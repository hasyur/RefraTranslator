"""Resolve exact Windows OCR wheel URLs, sizes and hashes without downloading wheels."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import deque
from importlib import metadata
from pathlib import Path
from urllib.parse import quote

import httpx
from pip._vendor.packaging.requirements import Requirement
from pip._vendor.packaging.tags import sys_tags
from pip._vendor.packaging.utils import canonicalize_name, parse_wheel_filename


ROOT_REQUIREMENTS = (
    "paddlepaddle-gpu==3.3.1",
    "paddleocr==3.7.0",
    "paddlex[ocr-core]==3.7.2",
)
PADDLE_GPU_WHEEL = {
    "name": "paddlepaddle-gpu",
    "version": "3.3.1",
    "url": (
        "https://paddle-whl.cdn.bcebos.com/stable/cu129/paddlepaddle-gpu/"
        "paddlepaddle_gpu-3.3.1-cp313-cp313-win_amd64.whl"
    ),
    "sha256": "71aed9d3d77f571eeee2e2deb6b33a06d18d82424bb04a81435480b7418fdab4",
    "size_bytes": 809_978_141,
}
PYPI_JSON = "https://pypi.org/pypi/{name}/{version}/json"
_WHEEL_SUFFIX = re.compile(r"\.whl(?:$|#)", re.IGNORECASE)


class ManifestError(RuntimeError):
    pass


def _installed_distribution(requirement: Requirement) -> metadata.Distribution:
    try:
        dist = metadata.distribution(requirement.name)
    except metadata.PackageNotFoundError as exc:
        raise ManifestError(
            f"OCR build environment is missing {requirement.name}; install the pinned OCR extra first"
        ) from exc
    version = dist.version
    if requirement.specifier and not requirement.specifier.contains(
        version,
        prereleases=True,
    ):
        raise ManifestError(
            f"OCR build environment has {requirement.name} {version}, "
            f"outside {requirement.specifier}"
        )
    return dist


def _installed_size_bytes(distribution: metadata.Distribution) -> int:
    total = 0
    for record in distribution.files or ():
        path = Path(distribution.locate_file(record))
        try:
            if path.is_file():
                total += path.stat().st_size
        except OSError:
            continue
    if total <= 0:
        raise ManifestError(
            f"Could not measure installed files for {distribution.metadata['Name']} {distribution.version}"
        )
    return total


def _resolve_installed_closure() -> tuple[metadata.Distribution, ...]:
    active_extras: dict[str, set[str]] = {}
    distributions: dict[str, metadata.Distribution] = {}
    pending: deque[tuple[Requirement, str]] = deque()
    for raw in ROOT_REQUIREMENTS:
        pending.append((Requirement(raw), "root"))
    processed_extras: dict[str, set[str]] = {}

    while pending:
        requirement, _parent = pending.popleft()
        key = canonicalize_name(requirement.name)
        distribution = _installed_distribution(requirement)
        distributions[key] = distribution
        extras = set(requirement.extras)
        known_extras = active_extras.setdefault(key, set())
        new_extras = extras - known_extras
        known_extras.update(extras)
        prior_extras = processed_extras.get(key, set())
        if key in processed_extras and not new_extras:
            continue
        processed_extras[key] = prior_extras | new_extras

        for raw_dependency in distribution.requires or ():
            dependency = Requirement(raw_dependency)
            if dependency.marker:
                contexts = {"", *known_extras}
                if not any(
                    dependency.marker.evaluate({"extra": extra})
                    for extra in contexts
                ):
                    continue
            pending.append((dependency, key))

    return tuple(distributions.values())


def _select_pypi_wheel(
    client: httpx.Client,
    distribution: metadata.Distribution,
    supported_tags: tuple,
) -> dict[str, object]:
    name = canonicalize_name(distribution.metadata["Name"])
    version = distribution.version
    url = PYPI_JSON.format(name=quote(name, safe="-._"), version=quote(version, safe="-._+"))
    try:
        response = client.get(url)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ManifestError(f"Could not read PyPI release metadata for {name} {version}: {exc}") from exc

    tag_rank = {tag: index for index, tag in enumerate(supported_tags)}
    candidates: list[tuple[int, dict[str, object]]] = []
    for file in payload.get("urls", ()):
        filename = file.get("filename", "")
        if not isinstance(filename, str) or not _WHEEL_SUFFIX.search(filename):
            continue
        try:
            wheel_name, _wheel_version, _build, wheel_tags = parse_wheel_filename(filename)
        except Exception:
            continue
        if canonicalize_name(wheel_name) != name:
            continue
        score = min((tag_rank[tag] for tag in wheel_tags if tag in tag_rank), default=None)
        if score is None:
            continue
        hashes = file.get("digests")
        sha256 = hashes.get("sha256") if isinstance(hashes, dict) else None
        size = file.get("size")
        file_url = file.get("url")
        if (
            not isinstance(sha256, str)
            or not re.fullmatch(r"[0-9a-fA-F]{64}", sha256)
            or not isinstance(size, int)
            or size <= 0
            or not isinstance(file_url, str)
            or not file_url.startswith("https://")
        ):
            continue
        candidates.append(
            (
                score,
                {
                    "name": distribution.metadata["Name"],
                    "version": version,
                    "url": file_url,
                    "sha256": sha256.lower(),
                    "size_bytes": size,
                },
            )
        )
    if not candidates:
        raise ManifestError(
            f"PyPI has no compatible Windows x64 wheel for {name} {version}"
        )
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def build_manifest(output: Path) -> None:
    if sys.version_info[:2] != (3, 13) or os.name != "nt" or sys.maxsize <= 2**32:
        raise ManifestError("Build the OCR manifest with 64-bit Windows CPython 3.13")
    distributions = _resolve_installed_closure()
    tags = tuple(sys_tags())
    paddle_name = canonicalize_name(PADDLE_GPU_WHEEL["name"])
    entries: list[dict[str, object]] = []
    timeout = httpx.Timeout(connect=20.0, read=45.0, write=20.0, pool=30.0)
    with httpx.Client(
        follow_redirects=True,
        timeout=timeout,
        headers={"Accept-Encoding": "identity", "User-Agent": "RefraTranslator build"},
    ) as client:
        for distribution in sorted(
            distributions,
            key=lambda item: canonicalize_name(item.metadata["Name"]),
        ):
            name = canonicalize_name(distribution.metadata["Name"])
            if name == paddle_name:
                entry = dict(PADDLE_GPU_WHEEL)
            else:
                entry = _select_pypi_wheel(client, distribution, tags)
            entry["installed_size_bytes"] = _installed_size_bytes(distribution)
            entries.append(entry)

    names = [canonicalize_name(str(entry["name"])) for entry in entries]
    if len(names) != len(set(names)):
        raise ManifestError("Dependency closure contains conflicting versions for a package")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".part")
    payload = {
        "schema_version": 1,
        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
        "platform": "win_amd64",
        "requirements": list(ROOT_REQUIREMENTS),
        "wheels": entries,
    }
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, output)
    total = sum(int(entry["size_bytes"]) for entry in entries)
    print(f"Wrote {len(entries)} wheel resources ({total:,} bytes) to {output}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        build_manifest(args.output)
    except (ManifestError, OSError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
