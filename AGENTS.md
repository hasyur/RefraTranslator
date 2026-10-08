## 注意事项

每次改动完成后，都必须Git commit，以便后续追踪和回滚。每次改动后，都必须编写或更新相关测试，并在交付给用户前，确保所有测试和验证全部通过。

## 两仓库上传规则

- 正式项目源码、正式测试和动态场景留在本公开仓库的 `origin`，审核后只从主仓库推送 `main`：`git push origin main`。
- 预览、原型、实验 benchmark 和非公开测试放在 `.local-tools` 的独立私有仓库，只推送它自己的私有 `origin` 的 `main`：`git -C .local-tools push origin main`。这些工具不是产品安装或运行前置，也不能进入公开仓库或源码包。
- 新环境先克隆公开项目，再从公开项目根目录把私有工具仓库克隆到 `.local-tools`。两个仓库分别测试、commit 和 push。
- 保留本地实验分支，不使用 `git push --all` 或 `git push --mirror`。
