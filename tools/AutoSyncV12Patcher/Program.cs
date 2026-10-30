using System.Diagnostics;
using System.IO.Compression;
using System.Security.Cryptography;
using System.Text;
using System.Windows.Forms;

namespace AutoSyncPatcher;

internal static class Program
{
    private const string PreviewUrl =
        "https://github.com/EVA0111/AutoSync/releases/download/preview-edit-20261030/AutoSync-PreviewEdit-Windows-Portable.zip";
    private const string OutputBaseName = "AutoSync-v1.2-PreviewEdit-Windows-Portable";

    [STAThread]
    private static async Task<int> Main(string[] args)
    {
        Console.OutputEncoding = Encoding.UTF8;
        Console.WriteLine("AutoSync v1.2 — Preview & Edit portable patcher");
        Console.WriteLine("Original files are NEVER overwritten.\n");
        try
        {
            if (args.Contains("--self-test"))
            {
                SelfTest();
                return 0;
            }
            if (args.Contains("--help"))
            {
                Console.WriteLine("Usage: AutoSync-v1.2-PreviewEdit-Patcher.exe [--source FOLDER] [--no-zip]");
                Console.WriteLine("Extract the v1.2 RAR before running. Needs an internet connection.");
                return 0;
            }

            string? given = ArgValue(args, "--source");
            string? selected = given is null ? DetectOrPickSource() : given;
            if (string.IsNullOrWhiteSpace(selected))
            {
                Console.WriteLine("Cancelled.");
                return 2;
            }
            string source = Path.GetFullPath(selected.Trim().Trim('"'));
            ValidateSource(source);
            Console.WriteLine("Source: " + source);
            bool noZip = args.Contains("--no-zip");
            string parent = Directory.GetParent(source)?.FullName
                ?? throw new InvalidOperationException("Cannot determine parent directory.");
            string output = UniqueOutput(parent, OutputBaseName);
            string outputZip = output + ".zip";
            if (Directory.Exists(output) || File.Exists(outputZip))
                throw new IOException("Output already exists: " + output);

            string temporary = Path.Combine(Path.GetTempPath(), "autosync-patcher-" +
                Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(temporary);
            bool createdDestination = false;
            try
            {
                Console.WriteLine("\n[1/6] Downloading Preview & Edit desktop app ...");
                string archive = Path.Combine(temporary, "preview.zip");
                using (var http = new HttpClient() { Timeout = TimeSpan.FromMinutes(15) })
                using (var response = await http.GetAsync(PreviewUrl, HttpCompletionOption.ResponseHeadersRead))
                {
                    response.EnsureSuccessStatusCode();
                    await using var input = await response.Content.ReadAsStreamAsync();
                    await using var file = File.Create(archive);
                    await input.CopyToAsync(file);
                }
                if (new FileInfo(archive).Length < 50 * 1024 * 1024)
                    throw new InvalidDataException("Downloaded Preview & Edit ZIP is unexpectedly small.");
                string expanded = Path.Combine(temporary, "unpacked");
                ZipFile.ExtractToDirectory(archive, expanded);
                string preview = Directory.EnumerateFiles(expanded, "AutoSync.exe", SearchOption.AllDirectories)
                    .Select(Path.GetDirectoryName)
                    .OfType<string>()
                    .FirstOrDefault(p => File.Exists(Path.Combine(p, "resources", "app.asar")))
                    ?? throw new InvalidDataException("The downloaded ZIP does not contain a complete AutoSync desktop app.");

                Console.WriteLine("[2/6] Installing the Preview & Edit desktop shell ...");
                Directory.CreateDirectory(output);
                createdDestination = true;
                CopyTree(preview, output, relative =>
                {
                    string local = relative.Replace('\\', '/');
                    return local.StartsWith("resources/engine/", StringComparison.OrdinalIgnoreCase) ||
                           local.StartsWith("resources/python/", StringComparison.OrdinalIgnoreCase);
                });

                Console.WriteLine("[3/6] Keeping your genuine v1.2 engine and Python runtime ...");
                string sourceEngine = Path.Combine(source, "resources", "engine");
                string sourcePython = Path.Combine(source, "resources", "python");
                string targetEngine = Path.Combine(output, "resources", "engine");
                string targetPython = Path.Combine(output, "resources", "python");
                CopyTree(sourceEngine, targetEngine);
                CopyTree(sourcePython, targetPython);

                // Some old portable releases bundle FFmpeg outside resources/engine.
                // Use the trusted GUI release's binaries only when the source lacks them.
                foreach (var name in new[] { "ffmpeg.exe", "ffprobe.exe" })
                {
                    string dst = Path.Combine(targetEngine, name);
                    if (!File.Exists(dst))
                    {
                        string src = Path.Combine(preview, "resources", "engine", name);
                        RequireFile(src, "FFmpeg dependency missing from preview package");
                        File.Copy(src, dst);
                    }
                }

                // Preserve any v1.2-only resource folders (not Electron app.asar or runtime).
                foreach (var entry in Directory.EnumerateFileSystemEntries(Path.Combine(source, "resources")))
                {
                    string name = Path.GetFileName(entry);
                    if (new[] { "engine", "python", "app.asar", "app.asar.unpacked" }
                        .Contains(name, StringComparer.OrdinalIgnoreCase))
                        continue;
                    string destination = Path.Combine(output, "resources", name);
                    if (Directory.Exists(entry))
                        CopyTree(entry, destination, onlyMissing: true);
                    else if (!File.Exists(destination))
                        File.Copy(entry, destination);
                }

                Console.WriteLine("[4/6] Checking engine and applying safe compatibility fix ...");
                VerifySame(sourceEngine, targetEngine, "autosync.py");
                VerifySame(sourceEngine, targetEngine, "desktop_bridge.py");

                // The original v1.2 engine sometimes passes an unsupported FFmpeg option.
                // Patch only this exact token in the copied engine; never touch the original.
                string videoEdits = Path.Combine(targetEngine, "video_edits.py");
                bool ffmpegFix = false;
                if (File.Exists(videoEdits))
                {
                    string oldText = File.ReadAllText(videoEdits);
                    string newText = oldText.Replace("'-filter_complex_script'", "'-/filter_complex'");
                    if (newText != oldText)
                    {
                        File.WriteAllText(videoEdits, newText, new UTF8Encoding(false));
                        ffmpegFix = true;
                    }
                }

                Console.WriteLine("[5/6] Testing copied Python and FFmpeg ...");
                string python = Path.Combine(targetPython, "python.exe");
                RunCheck(python, ["-c", "import numpy, scipy; print('Python dependencies OK')"], targetEngine);
                RunCheck(python, [Path.Combine(targetEngine, "autosync.py"), "--help"], targetEngine);
                RunCheck(Path.Combine(targetEngine, "ffmpeg.exe"), ["-version"], targetEngine);
                RunCheck(Path.Combine(targetEngine, "ffprobe.exe"), ["-version"], targetEngine);
                File.WriteAllText(Path.Combine(output, "PATCH-INFO.txt"), string.Join("\r\n", [
                    "AutoSync v1.2 + Preview & Edit",
                    "Built locally by the one-click patcher.",
                    "SOURCE: " + source,
                    "Your v1.2 Python engine and runtime were copied, not downgraded.",
                    "The Preview & Edit GUI comes from the public Electron preview release.",
                    "FFmpeg filter_complex_script compatibility fix applied: " + ffmpegFix,
                    "NOTE: The original GUI may still display v1.1 labels inherited from the preview shell.",
                    "NOTE: This patcher does not replace v1.2's automatic matching algorithm.",
                    "NOTE: For case 1, analyze again with the full opening retained; a previous edited plan cannot restore cut frames.",
                    "NOTE: The editor and real-media output still require manual listening/verification.",
                    "The original installation was not modified."
                ]) + "\r\n", new UTF8Encoding(false));

                if (!noZip)
                {
                    Console.WriteLine("[6/6] Creating self-contained portable ZIP ...");
                    ZipFile.CreateFromDirectory(output, outputZip, CompressionLevel.Optimal, includeBaseDirectory: true);
                }
                else Console.WriteLine("[6/6] ZIP skipped (--no-zip).");
                Console.WriteLine("\nSUCCESS");
                Console.WriteLine("Portable folder: " + output);
                if (!noZip) Console.WriteLine("Portable ZIP: " + outputZip);
                Console.WriteLine("Run AutoSync.exe from the new folder.");
                return 0;
            }
            catch
            {
                // Never leave a half-created folder that might be mistaken for a complete app.
                if (createdDestination && Directory.Exists(output))
                {
                    try { Directory.Delete(output, true); }
                    catch { Console.WriteLine("WARNING: Could not remove partial output folder: " + output); }
                }
                if (File.Exists(outputZip))
                {
                    try { File.Delete(outputZip); } catch { }
                }
                throw;
            }
            finally
            {
                try { Directory.Delete(temporary, recursive: true); } catch { }
            }
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine("\nPATCH FAILED: " + ex.Message);
            Console.Error.WriteLine("The original AutoSync installation was left unchanged.");
            return 1;
        }
        finally
        {
            if (Environment.UserInteractive && !args.Contains("--no-pause") &&
                !args.Contains("--self-test") && !args.Contains("--help"))
            {
                Console.WriteLine("\nPress Enter to close.");
                Console.ReadLine();
            }
        }
    }

    private static string? ArgValue(string[] args, string name)
    {
        for (int i = 0; i < args.Length; i++)
        {
            if (args[i] == name)
            {
                if (i + 1 >= args.Length) throw new ArgumentException(name + " requires a folder.");
                return args[i + 1];
            }
        }
        return null;
    }

    private static string? DetectOrPickSource()
    {
        string folder = AppContext.BaseDirectory.TrimEnd(Path.DirectorySeparatorChar);
        if (LooksLikeSource(folder)) return folder;
        Console.WriteLine("Select the extracted AutoSync v1.2 portable folder.");
        using var picker = new FolderBrowserDialog
        {
            Description = "Choose the folder that contains AutoSync.exe and resources",
            UseDescriptionForTitle = true,
            ShowNewFolderButton = false,
            InitialDirectory = Directory.Exists(folder) ? folder : Environment.GetFolderPath(Environment.SpecialFolder.UserProfile)
        };
        return picker.ShowDialog() == DialogResult.OK ? picker.SelectedPath : null;
    }

    private static bool LooksLikeSource(string folder) =>
        File.Exists(Path.Combine(folder, "AutoSync.exe")) &&
        File.Exists(Path.Combine(folder, "resources", "engine", "autosync.py")) &&
        File.Exists(Path.Combine(folder, "resources", "python", "python.exe"));

    private static void ValidateSource(string folder)
    {
        if (!Directory.Exists(folder)) throw new DirectoryNotFoundException(folder);
        if (!LooksLikeSource(folder))
            throw new IOException("Select the EXTRACTED AutoSync v1.2 folder with AutoSync.exe, resources\\engine and resources\\python. RAR input is not supported directly.");
        string name = Path.GetFileName(folder.TrimEnd('\\', '/'));
        if (name.Contains("v1.3", StringComparison.OrdinalIgnoreCase))
            throw new IOException("This appears to be a v1.3 installation. The patcher is designed for v1.2.");
    }

    private static string UniqueOutput(string parent, string baseName)
    {
        for (int i = 0; i < 100; i++)
        {
            string name = i == 0 ? baseName : baseName + "-" + i.ToString("00");
            string full = Path.Combine(parent, name);
            if (!Directory.Exists(full) && !File.Exists(full + ".zip")) return full;
        }
        throw new IOException("No unused output folder name is available.");
    }

    private static void CopyTree(string src, string dst, Func<string, bool>? skip = null, bool onlyMissing = false)
    {
        if (!Directory.Exists(src)) throw new DirectoryNotFoundException(src);
        Directory.CreateDirectory(dst);
        foreach (string directory in Directory.EnumerateDirectories(src, "*", SearchOption.AllDirectories))
        {
            string rel = Path.GetRelativePath(src, directory);
            if (skip?.Invoke(rel + Path.DirectorySeparatorChar) == true) continue;
            Directory.CreateDirectory(Path.Combine(dst, rel));
        }
        foreach (string file in Directory.EnumerateFiles(src, "*", SearchOption.AllDirectories))
        {
            string rel = Path.GetRelativePath(src, file);
            if (skip?.Invoke(rel) == true) continue;
            string target = Path.Combine(dst, rel);
            Directory.CreateDirectory(Path.GetDirectoryName(target)!);
            if (!onlyMissing || !File.Exists(target)) File.Copy(file, target, overwrite: !onlyMissing);
        }
    }

    private static void RequireFile(string path, string reason)
    {
        if (!File.Exists(path)) throw new FileNotFoundException(reason, path);
    }

    private static void VerifySame(string original, string copy, string name)
    {
        string first = Path.Combine(original, name), second = Path.Combine(copy, name);
        RequireFile(first, "Missing original engine file: " + name);
        RequireFile(second, "Missing copied engine file: " + name);
        using var src = File.OpenRead(first);
        using var dst = File.OpenRead(second);
        if (!SHA256.HashData(src).SequenceEqual(SHA256.HashData(dst)))
            throw new InvalidDataException("Engine file changed unexpectedly: " + name);
    }

    private static void RunCheck(string executable, IEnumerable<string> arguments, string workingDirectory)
    {
        RequireFile(executable, "Bundled executable missing");
        using var process = new Process();
        process.StartInfo.FileName = executable;
        process.StartInfo.WorkingDirectory = workingDirectory;
        process.StartInfo.UseShellExecute = false;
        process.StartInfo.CreateNoWindow = true;
        process.StartInfo.RedirectStandardOutput = true;
        process.StartInfo.RedirectStandardError = true;
        foreach (var argument in arguments) process.StartInfo.ArgumentList.Add(argument);
        process.Start();
        Task<string> stdout = process.StandardOutput.ReadToEndAsync();
        Task<string> stderr = process.StandardError.ReadToEndAsync();
        if (!process.WaitForExit(90_000))
        {
            process.Kill(entireProcessTree: true);
            throw new TimeoutException(Path.GetFileName(executable) + " did not finish its smoke test.");
        }
        string error = stderr.GetAwaiter().GetResult();
        _ = stdout.GetAwaiter().GetResult();
        if (process.ExitCode != 0)
            throw new IOException("Smoke test failed for " + Path.GetFileName(executable) + ": " + error[..Math.Min(error.Length, 1200)]);
    }

    private static void SelfTest()
    {
        string testRoot = Path.Combine(Path.GetTempPath(), "AutoSync test folder " + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(testRoot);
        try
        {
            string folder = Path.Combine(testRoot, "AutoSync-v1.2-Windows-Portable");
            Directory.CreateDirectory(folder);
            try
            {
                ValidateSource(folder);
                throw new InvalidOperationException("Expected missing-installation validation failure.");
            }
            catch (IOException) { }
            string unique = UniqueOutput(testRoot, OutputBaseName);
            if (!unique.Contains(OutputBaseName)) throw new InvalidOperationException("Output directory generation failed.");
            string sourceTree = Path.Combine(testRoot, "sample");
            string destTree = Path.Combine(testRoot, "copy");
            Directory.CreateDirectory(Path.Combine(sourceTree, "resources", "engine"));
            Directory.CreateDirectory(Path.Combine(sourceTree, "resources", "python"));
            File.WriteAllText(Path.Combine(sourceTree, "resources", "engine", "autosync.py"), "ok");
            File.WriteAllText(Path.Combine(sourceTree, "resources", "python", "python.exe"), "ok");
            CopyTree(sourceTree, destTree, rel => rel.Replace('\\','/').StartsWith("resources/engine/", StringComparison.OrdinalIgnoreCase));
            if (File.Exists(Path.Combine(destTree, "resources", "engine", "autosync.py")))
                throw new InvalidOperationException("Engine copy exclusion failed.");
            if (!File.Exists(Path.Combine(destTree, "resources", "python", "python.exe")))
                throw new InvalidOperationException("Non-excluded files were not copied.");
            Console.WriteLine("Patcher self-test PASSED");
        }
        finally { try { Directory.Delete(testRoot, true); } catch { } }
    }
}
