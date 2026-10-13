using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;

[assembly: AssemblyTitle("RefraTranslator")]
[assembly: AssemblyDescription("RefraTranslator Windows application launcher")]
[assembly: AssemblyProduct("RefraTranslator")]
[assembly: AssemblyVersion("0.1.0.0")]
[assembly: AssemblyFileVersion("0.1.0.0")]

internal static class RefraTranslatorLauncher
{
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern int MessageBoxW(IntPtr owner, string message, string title, uint flags);

    // ProcessStartInfo.Arguments uses Windows command-line quoting on .NET Framework.
    // Quote every forwarded argument, including empty values and trailing backslashes.
    private static string QuoteArgument(string argument)
    {
        StringBuilder quoted = new StringBuilder("\"");
        int backslashes = 0;
        foreach (char character in argument)
        {
            if (character == '\\')
            {
                backslashes++;
                continue;
            }
            if (character == '"')
            {
                quoted.Append('\\', backslashes * 2 + 1);
            }
            else
            {
                quoted.Append('\\', backslashes);
            }
            quoted.Append(character);
            backslashes = 0;
        }
        quoted.Append('\\', backslashes * 2);
        quoted.Append('"');
        return quoted.ToString();
    }

    [STAThread]
    private static int Main(string[] arguments)
    {
        try
        {
            string installRoot = AppDomain.CurrentDomain.BaseDirectory;
            string python = Path.Combine(installRoot, "runtime", "pythonw.exe");
            if (!File.Exists(python))
            {
                throw new FileNotFoundException("缺少内置运行环境，请重新安装 RefraTranslator。", python);
            }

            StringBuilder command = new StringBuilder(
                "-s -X utf8 -m game_screen_translator.gui_entry --installed");
            foreach (string argument in arguments)
            {
                command.Append(' ');
                command.Append(QuoteArgument(argument));
            }

            ProcessStartInfo start = new ProcessStartInfo();
            start.FileName = python;
            start.Arguments = command.ToString();
            start.WorkingDirectory = installRoot;
            start.UseShellExecute = false;
            start.CreateNoWindow = true;
            using (Process process = Process.Start(start))
            {
                if (process == null)
                {
                    throw new InvalidOperationException("无法启动内置运行环境。");
                }
                process.WaitForExit();
                return process.ExitCode;
            }
        }
        catch (Exception error)
        {
            MessageBoxW(IntPtr.Zero, "RefraTranslator 无法启动。\n\n" + error.Message,
                "RefraTranslator", 0x10);
            return 1;
        }
    }
}
