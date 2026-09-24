// KineCapture Windows kurucusu (ve kaldırıcısı).
//
// Tek dosya: bu programın sonuna eklenmiş ZIP yükü, conda ortamını ve kurulum
// tanımını (install.json) taşır. Sıra değişmez:
//
//   ön denetim -> ortamı açma -> conda-unpack -> modül derleme ->
//   kısayollar ve kaldırma kaydı -> kurulum sonrası doğrulama
//
// Ön denetim geçmezse makinede hiçbir şey değişmez; yalnız %TEMP% altına bir
// log yazılır. Windows'un kendi .NET Framework 4.x derleyicisiyle (csc.exe)
// derlenir; indirme gerektiren hiçbir araç kullanılmaz. Derleme:
// scripts/release/build_installer.ps1. Ön denetim kuralları ve kaynakları:
// knowledge/reports/release-installer-phase-b-2026-09-23.md.
//
// Komut satırı:
//   /checkonly        yalnız denetle; hiçbir şey kurma
//   /silent           arayüzsüz; sonuç çıkış kodunda ve logda
//   /dir=<klasör>     kurulum klasörü (varsayılan %LOCALAPPDATA%\Programs\KineCapture)
//   /log=<dosya>      log dosyası (varsayılan %TEMP%\KineCapture-Setup-<zaman>.log)
//   /report=<dosya>   denetim/kurulum sonucunu JSON olarak da yaz
//   /nodesktop        masaüstü kısayolu oluşturma
//   /noshortcuts      hiç kısayol oluşturma (testler)
//   /regkey=<ad>      kaldırma kaydının anahtar adı (testler)
//   /facts=<json>     makineyi yoklamak yerine bu olguları kullan (testler)
//   /sdkroot=<klasör> ZED SDK'yı bu klasörde ara (testler)
//   /uninstall        kaldır (kurulu uninstall.exe bununla çalışır)
//
// Çıkış kodları: 0 tamam, 1 beklenmeyen hata, 2 ön denetim geçmedi,
// 3 kurulum/doğrulama başarısız, 4 kullanıcı vazgeçti, 5 geçersiz kullanım.

using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Globalization;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Management;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Win32;

[assembly: AssemblyTitle("KineCapture Kurulum")]
[assembly: AssemblyProduct("KineCapture")]
[assembly: AssemblyCompany("KineCapture")]
[assembly: AssemblyVersion("1.0.0.0")]
// Without this the runtime assumes a pre-4.6.2 program and keeps the legacy
// path checks (248-character folders) that a deep conda tree runs into.
[assembly: System.Runtime.Versioning.TargetFramework(".NETFramework,Version=v4.8", FrameworkDisplayName = ".NET Framework 4.8")]

namespace KineCaptureSetup
{
    static class ExitCode
    {
        public const int Ok = 0;
        public const int Error = 1;
        public const int PreflightFailed = 2;
        public const int InstallFailed = 3;
        public const int Cancelled = 4;
        public const int Usage = 5;
    }

    // ================================================================ options
    sealed class Options
    {
        public bool CheckOnly, Silent, Uninstall, NoShortcuts, NoDesktop;
        public string Dir, LogPath, FactsPath, SdkRoot, ReportPath;
        public string RegKey = "KineCapture";

        public static Options Parse(string[] args)
        {
            var options = new Options();
            foreach (string raw in args)
            {
                string arg = raw.Trim();
                if (arg.Length == 0) continue;
                string name = arg.TrimStart('/', '-');
                string value = null;
                int eq = name.IndexOf('=');
                if (eq >= 0)
                {
                    value = name.Substring(eq + 1).Trim().Trim('"');
                    name = name.Substring(0, eq);
                }
                switch (name.ToLowerInvariant())
                {
                    case "checkonly": options.CheckOnly = true; break;
                    case "silent": case "quiet": case "q": options.Silent = true; break;
                    case "uninstall": options.Uninstall = true; break;
                    case "noshortcuts": options.NoShortcuts = true; break;
                    case "nodesktop": options.NoDesktop = true; break;
                    case "dir": options.Dir = value; break;
                    case "log": options.LogPath = value; break;
                    case "report": options.ReportPath = value; break;
                    case "facts": options.FactsPath = value; break;
                    case "sdkroot": options.SdkRoot = value; break;
                    case "regkey": options.RegKey = value; break;
                    default: throw new ArgumentException("Bilinmeyen seçenek: " + raw);
                }
            }
            if (string.IsNullOrEmpty(options.RegKey) || options.RegKey.IndexOfAny(new[] { '\\', '/' }) >= 0)
                throw new ArgumentException("Geçersiz /regkey değeri.");
            return options;
        }
    }

    // ==================================================================== log
    sealed class Log : IDisposable
    {
        readonly object gate = new object();
        StreamWriter writer;
        public readonly string FilePath;
        public event Action<string> Line;

        public Log(string path)
        {
            FilePath = path;
            try
            {
                Directory.CreateDirectory(Path.GetDirectoryName(path));
                var stream = new FileStream(path, FileMode.Append, FileAccess.Write, FileShare.ReadWrite);
                writer = new StreamWriter(stream, new UTF8Encoding(false));
                writer.AutoFlush = true;
            }
            catch (Exception) { writer = null; }
        }

        public void Info(string text) { Write("BİLGİ", text); }
        public void Warn(string text) { Write("UYARI", text); }
        public void Error(string text) { Write("HATA ", text); }

        void Write(string level, string text)
        {
            string stamp = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss", CultureInfo.InvariantCulture);
            lock (gate)
            {
                if (writer != null)
                {
                    foreach (string line in text.Replace("\r\n", "\n").Split('\n'))
                        writer.WriteLine(stamp + " " + level + " " + line);
                }
            }
            var handler = Line;
            if (handler != null) handler(text);
        }

        public void CopyTo(string destination)
        {
            lock (gate)
            {
                using (var input = new FileStream(FilePath, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
                using (var output = new FileStream(destination, FileMode.Create, FileAccess.Write))
                    input.CopyTo(output);
            }
        }

        public void Dispose()
        {
            lock (gate)
            {
                if (writer != null) writer.Dispose();
                writer = null;
            }
        }
    }

    // A child with no standard handles at all - what a Start-menu shortcut
    // gives pythonw.exe. Process.Start cannot promise that: with no
    // redirection it hands the child whatever handles this process has.
    static class Detached
    {
        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
        struct StartupInfo
        {
            public int cb;
            public string lpReserved, lpDesktop, lpTitle;
            public int dwX, dwY, dwXSize, dwYSize, dwXCountChars, dwYCountChars, dwFillAttribute, dwFlags;
            public short wShowWindow, cbReserved2;
            public IntPtr lpReserved2, hStdInput, hStdOutput, hStdError;
        }

        [StructLayout(LayoutKind.Sequential)]
        struct ProcessInformation
        {
            public IntPtr hProcess, hThread;
            public int dwProcessId, dwThreadId;
        }

        [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
        static extern bool CreateProcessW(string application, StringBuilder commandLine, IntPtr processAttributes,
            IntPtr threadAttributes, bool inheritHandles, uint creationFlags, string environment,
            string currentDirectory, ref StartupInfo startupInfo, out ProcessInformation processInformation);

        [DllImport("kernel32.dll", SetLastError = true)]
        static extern uint WaitForSingleObject(IntPtr handle, uint milliseconds);

        [DllImport("kernel32.dll", SetLastError = true)]
        static extern bool GetExitCodeProcess(IntPtr process, out uint exitCode);

        [DllImport("kernel32.dll", SetLastError = true)]
        static extern bool TerminateProcess(IntPtr process, uint exitCode);

        [DllImport("kernel32.dll", SetLastError = true)]
        static extern bool CloseHandle(IntPtr handle);

        const uint CreateNoWindow = 0x08000000, CreateUnicodeEnvironment = 0x00000400, StartfUseStdHandles = 0x00000100;

        public static int Run(string exe, string args, string cwd, IDictionary<string, string> environment, int timeoutMs)
        {
            var info = new StartupInfo();
            info.cb = Marshal.SizeOf(typeof(StartupInfo));
            info.dwFlags = (int)StartfUseStdHandles;  // and every handle zero
            var block = new StringBuilder();
            foreach (var pair in environment.OrderBy(p => p.Key, StringComparer.OrdinalIgnoreCase))
                block.Append(pair.Key).Append('=').Append(pair.Value).Append('\0');
            block.Append('\0');
            ProcessInformation process;
            var command = new StringBuilder("\"" + exe + "\" " + args);
            if (!CreateProcessW(exe, command, IntPtr.Zero, IntPtr.Zero, false, CreateNoWindow | CreateUnicodeEnvironment,
                    block.ToString(), cwd, ref info, out process))
                throw new StepFailed("Başlatılamadı (" + Marshal.GetLastWin32Error() + "): " + exe);
            try
            {
                if (WaitForSingleObject(process.hProcess, (uint)timeoutMs) != 0)
                {
                    TerminateProcess(process.hProcess, 1);
                    throw new StepFailed(Path.GetFileName(exe) + " zaman aşımına uğradı (" + timeoutMs / 1000 + " s).");
                }
                uint code;
                GetExitCodeProcess(process.hProcess, out code);
                return (int)code;
            }
            finally
            {
                CloseHandle(process.hThread);
                CloseHandle(process.hProcess);
            }
        }
    }

    static class Json
    {
        public static JavaScriptSerializer Serializer()
        {
            var serializer = new JavaScriptSerializer();
            serializer.MaxJsonLength = int.MaxValue;
            return serializer;
        }

        public static Dictionary<string, object> ParseObject(string text)
        {
            var parsed = Serializer().DeserializeObject(text) as Dictionary<string, object>;
            if (parsed == null) throw new InvalidDataException("JSON nesnesi bekleniyordu.");
            return parsed;
        }

        public static string Write(object value)
        {
            return Serializer().Serialize(value);
        }

        public static string Str(IDictionary<string, object> map, string key)
        {
            object value;
            if (map == null || !map.TryGetValue(key, out value) || value == null) return null;
            return Convert.ToString(value, CultureInfo.InvariantCulture);
        }

        public static long Long(IDictionary<string, object> map, string key, long fallback)
        {
            object value;
            if (map == null || !map.TryGetValue(key, out value) || value == null) return fallback;
            try { return Convert.ToInt64(value, CultureInfo.InvariantCulture); }
            catch (Exception) { return fallback; }
        }

        public static bool Bool(IDictionary<string, object> map, string key, bool fallback)
        {
            object value;
            if (map == null || !map.TryGetValue(key, out value) || value == null) return fallback;
            if (value is bool) return (bool)value;
            return fallback;
        }

        public static List<string> Strings(IDictionary<string, object> map, string key)
        {
            var result = new List<string>();
            object value;
            if (map == null || !map.TryGetValue(key, out value) || value == null) return result;
            var items = value as IEnumerable;
            if (items == null || value is string) return result;
            foreach (object item in items) if (item != null) result.Add(Convert.ToString(item, CultureInfo.InvariantCulture));
            return result;
        }
    }

    // ======================================================== user locations
    static class Places
    {
        // Environment variables first, so a test (or a second Windows user
        // simulated in a sandbox) can redirect every location the installer
        // touches; the shell's own answer is the fallback.
        static string Env(string name, Environment.SpecialFolder fallback)
        {
            string value = Environment.GetEnvironmentVariable(name);
            if (!string.IsNullOrEmpty(value)) return value;
            return Environment.GetFolderPath(fallback);
        }

        public static string LocalAppData { get { return Env("LOCALAPPDATA", Environment.SpecialFolder.LocalApplicationData); } }
        public static string AppData { get { return Env("APPDATA", Environment.SpecialFolder.ApplicationData); } }
        public static string Temp { get { return Path.GetTempPath(); } }

        public static string DefaultTarget
        {
            get { return Path.Combine(LocalAppData, "Programs", "KineCapture"); }
        }

        public static string StartMenuDir
        {
            get { return Path.Combine(AppData, "Microsoft", "Windows", "Start Menu", "Programs"); }
        }

        public static string Desktop
        {
            get
            {
                string profile = Environment.GetEnvironmentVariable("USERPROFILE");
                string real = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
                // Under a redirected profile (tests) the desktop moves with it.
                if (!string.IsNullOrEmpty(profile) && !string.Equals(Path.GetFullPath(profile).TrimEnd('\\'),
                        Path.GetFullPath(real).TrimEnd('\\'), StringComparison.OrdinalIgnoreCase))
                    return Path.Combine(profile, "Desktop");
                return Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
            }
        }
    }

    // ================================================================ payload
    sealed class SubStream : Stream
    {
        readonly Stream inner;
        readonly long start, length;
        long position;

        public SubStream(Stream inner, long start, long length)
        {
            this.inner = inner; this.start = start; this.length = length;
        }

        public override bool CanRead { get { return true; } }
        public override bool CanSeek { get { return true; } }
        public override bool CanWrite { get { return false; } }
        public override long Length { get { return length; } }
        public override long Position { get { return position; } set { position = value; } }

        public override int Read(byte[] buffer, int offset, int count)
        {
            long remaining = length - position;
            if (remaining <= 0) return 0;
            if (count > remaining) count = (int)remaining;
            if (inner.Position != start + position) inner.Position = start + position;
            int read = inner.Read(buffer, offset, count);
            position += read;
            return read;
        }

        public override long Seek(long offset, SeekOrigin origin)
        {
            long target = origin == SeekOrigin.Begin ? offset : origin == SeekOrigin.Current ? position + offset : length + offset;
            if (target < 0) throw new IOException("Yükün başından önceye gidilemez.");
            position = target;
            return position;
        }

        public override void Flush() { }
        public override void SetLength(long value) { throw new NotSupportedException(); }
        public override void Write(byte[] buffer, int offset, int count) { throw new NotSupportedException(); }
    }

    sealed class Payload : IDisposable
    {
        public static readonly byte[] Magic = Encoding.ASCII.GetBytes("KCSETUP1");
        public const string InstallFile = "install.json";

        readonly FileStream file;
        public readonly long Offset, Length;
        public readonly ZipArchive Archive;
        public readonly Dictionary<string, object> Install;

        Payload(FileStream file, long offset, long length)
        {
            this.file = file; Offset = offset; Length = length;
            Archive = new ZipArchive(new SubStream(file, offset, length), ZipArchiveMode.Read, false, Encoding.UTF8);
            ZipArchiveEntry entry = Archive.GetEntry(InstallFile);
            if (entry == null) throw new InvalidDataException("Kurulum yükünde " + InstallFile + " yok.");
            using (var reader = new StreamReader(entry.Open(), Encoding.UTF8))
                Install = Json.ParseObject(reader.ReadToEnd());
        }

        // null when the program carries no payload (the installed uninstaller).
        public static Payload Open(string exePath)
        {
            var file = new FileStream(exePath, FileMode.Open, FileAccess.Read, FileShare.Read, 1 << 20);
            try
            {
                if (file.Length < 16) { file.Dispose(); return null; }
                var trailer = new byte[16];
                file.Position = file.Length - 16;
                ReadExactly(file, trailer);
                for (int i = 0; i < 8; i++)
                    if (trailer[8 + i] != Magic[i]) { file.Dispose(); return null; }
                long length = BitConverter.ToInt64(trailer, 0);
                long offset = file.Length - 16 - length;
                if (length <= 0 || offset <= 0) throw new InvalidDataException("Kurulum yükü bozuk.");
                return new Payload(file, offset, length);
            }
            catch
            {
                file.Dispose();
                throw;
            }
        }

        static void ReadExactly(Stream stream, byte[] buffer)
        {
            int done = 0;
            while (done < buffer.Length)
            {
                int read = stream.Read(buffer, done, buffer.Length - done);
                if (read <= 0) throw new EndOfStreamException();
                done += read;
            }
        }

        // The program itself without its payload: the installed uninstaller.
        public void WriteStub(string path)
        {
            using (var output = new FileStream(path, FileMode.Create, FileAccess.Write))
            {
                file.Position = 0;
                var buffer = new byte[1 << 20];
                long left = Offset;
                while (left > 0)
                {
                    int read = file.Read(buffer, 0, (int)Math.Min(buffer.Length, left));
                    if (read <= 0) throw new EndOfStreamException();
                    output.Write(buffer, 0, read);
                    left -= read;
                }
            }
        }

        public string Version { get { return Json.Str(Install, "version") ?? "?"; } }
        public string Product { get { return Json.Str(Install, "product") ?? "KineCapture"; } }

        public void Dispose()
        {
            Archive.Dispose();
            file.Dispose();
        }
    }

    // ============================================================= preflight
    sealed class Requirements
    {
        public string ZedSdk = "5.4.1";
        public int CudaMajor = 13;       // what the release was built against
        public long RequiredBytes;       // unpacked size plus compiled modules
        public int MaxRelativePath;      // longest path inside the installation

        // NVIDIA's minimum driver for CUDA minor-version compatibility, by the
        // CUDA major version the ZED SDK was built with (zed-config.cmake,
        // ZED_CUDA_VERSION). Sources, read 23 September 2026:
        //   13.x: ">= 580" - CUDA Toolkit release notes (current), table
        //         "Driver Range for Minor Version Compatibility"; the CUDA
        //         13.0 notes list Windows as N/A because the Windows driver
        //         is no longer bundled, so the R580 branch is the floor.
        //   12.x: Windows ">=527.41" - CUDA 12.0.0 release notes (archive),
        //         "Minimum Required Driver Version for CUDA Minor Version
        //         Compatibility".
        // Details: knowledge/reports/release-installer-phase-b-2026-09-23.md.
        public static readonly Dictionary<int, string> MinDriverByCuda = new Dictionary<int, string>
        {
            { 13, "580.00" },
            { 12, "527.41" },
        };

        public static Requirements From(Dictionary<string, object> install)
        {
            var result = new Requirements();
            if (install == null) return result;
            object value;
            if (install.TryGetValue("requirements", out value))
            {
                var map = value as Dictionary<string, object>;
                if (map != null)
                {
                    result.ZedSdk = Json.Str(map, "zed_sdk") ?? result.ZedSdk;
                    result.CudaMajor = (int)Json.Long(map, "cuda_major", result.CudaMajor);
                    result.RequiredBytes = Json.Long(map, "required_bytes", 0);
                    result.MaxRelativePath = (int)Json.Long(map, "max_relative_path", 0);
                }
            }
            return result;
        }
    }

    sealed class Check
    {
        public string Id, Title, Found, Needed, Remedy;
        public bool Ok;

        public Dictionary<string, object> ToMap()
        {
            return new Dictionary<string, object>
            {
                { "id", Id }, { "title", Title }, { "ok", Ok },
                { "found", Found }, { "needed", Needed }, { "remedy", Ok ? "" : Remedy },
            };
        }
    }

    static class Preflight
    {
        public const string ZedUninstallKey =
            @"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{A9F85810-3642-4527-82DC-9169B5A855D0}_is1";
        public static readonly string[] SdkDlls =
            { "sl_zed64.dll", "sl_ai64.dll", "nvinfer_10.dll", "nvinfer_plugin_10.dll", "nvonnxparser_10.dll" };
        public static readonly string[] DriverDlls = { "nvcuda.dll", "nvcuvid.dll", "nvEncodeAPI64.dll" };
        public static readonly string[] VcDlls =
            { "msvcp140.dll", "vcruntime140.dll", "vcruntime140_1.dll", "mfc140.dll", "vcomp140.dll", "concrt140.dll" };
        public const string DefaultSdkRoot = @"C:\Program Files (x86)\ZED SDK";
        public const int MaxPath = 259;

        // ------------------------------------------------------------ gather
        public static Dictionary<string, object> Gather(string sdkRootOverride, string target, Log log)
        {
            var facts = new Dictionary<string, object>();
            Guard(log, "işletim sistemi", delegate { GatherOs(facts); });
            Guard(log, "ZED SDK", delegate { GatherZed(facts, sdkRootOverride); });
            Guard(log, "ekran kartı", delegate { GatherGpu(facts); });
            Guard(log, "sistem DLL'leri", delegate
            {
                string system = Environment.GetFolderPath(Environment.SpecialFolder.System);
                facts["driver_dlls_missing"] = SdkMissing(system, DriverDlls);
                facts["vc_dlls_missing"] = SdkMissing(system, VcDlls);
                facts["vc_redist_version"] = VcRedistVersion();
            });
            Guard(log, "disk", delegate { GatherDisk(facts, target); });
            return facts;
        }

        static void Guard(Log log, string what, Action action)
        {
            try { action(); }
            catch (Exception exc) { if (log != null) log.Warn(what + " yoklanamadı: " + exc.Message); }
        }

        static void GatherOs(Dictionary<string, object> facts)
        {
            facts["os_64bit"] = Environment.Is64BitOperatingSystem;
            using (var key = RegistryKey.OpenBaseKey(RegistryHive.LocalMachine, RegistryView.Registry64)
                       .OpenSubKey(@"SOFTWARE\Microsoft\Windows NT\CurrentVersion"))
            {
                if (key == null) return;
                object major = key.GetValue("CurrentMajorVersionNumber");
                object build = key.GetValue("CurrentBuildNumber");
                facts["os_major"] = major != null ? Convert.ToInt64(major) : 0L;
                long buildNumber = 0;
                long.TryParse(Convert.ToString(build), NumberStyles.Integer, CultureInfo.InvariantCulture, out buildNumber);
                facts["os_build"] = buildNumber;
                facts["os_edition"] = Convert.ToString(key.GetValue("EditionID"));
                facts["os_display_version"] = Convert.ToString(key.GetValue("DisplayVersion"));
            }
        }

        static void GatherZed(Dictionary<string, object> facts, string sdkRootOverride)
        {
            string root = null, source = null;
            string registryVersion = null, registryLocation = null;
            using (var hklm32 = RegistryKey.OpenBaseKey(RegistryHive.LocalMachine, RegistryView.Registry32))
            using (var key = hklm32.OpenSubKey(ZedUninstallKey))
            {
                if (key != null)
                {
                    registryVersion = Convert.ToString(key.GetValue("DisplayVersion"));
                    registryLocation = Convert.ToString(key.GetValue("InstallLocation"));
                }
            }
            if (!string.IsNullOrEmpty(sdkRootOverride))
            {
                root = sdkRootOverride; source = "override";
                registryVersion = null;  // a test tree has no uninstall entry
            }
            else
            {
                string env = Environment.GetEnvironmentVariable("ZED_SDK_ROOT_DIR");
                if (!string.IsNullOrEmpty(env) && Directory.Exists(env)) { root = env; source = "ZED_SDK_ROOT_DIR"; }
                else if (!string.IsNullOrEmpty(registryLocation) && Directory.Exists(registryLocation))
                { root = registryLocation; source = "kayıt defteri (InstallLocation)"; }
                else if (Directory.Exists(DefaultSdkRoot)) { root = DefaultSdkRoot; source = "varsayılan konum"; }
            }
            facts["zed_registry_version"] = registryVersion;
            if (root == null || !Directory.Exists(root))
            {
                facts["zed_root"] = null;
                return;
            }
            root = root.TrimEnd('\\');
            facts["zed_root"] = root;
            facts["zed_root_source"] = source;
            facts["zed_header_version"] = HeaderVersion(Path.Combine(root, "include", "sl", "Camera.hpp"));
            facts["zed_cmake_version"] = CmakeValue(Path.Combine(root, "zed-config-version.cmake"),
                @"set\(\s*PACKAGE_VERSION\s+""([0-9.]+)""\s*\)");
            string cuda = CmakeValue(Path.Combine(root, "zed-config.cmake"), @"SET\(\s*ZED_CUDA_VERSION\s+([0-9]+)\s*\)");
            facts["zed_cuda_major"] = cuda == null ? (object)null : long.Parse(cuda, CultureInfo.InvariantCulture);
            string bin = Path.Combine(root, "bin");
            facts["zed_bin"] = bin;
            facts["zed_dlls_missing"] = SdkMissing(bin, SdkDlls);
            facts["zed_bin_on_path"] = OnPath(bin);
        }

        public static string HeaderVersion(string header)
        {
            if (!File.Exists(header)) return null;
            string text = File.ReadAllText(header);
            string major = Macro(text, "ZED_SDK_MAJOR_VERSION");
            string minor = Macro(text, "ZED_SDK_MINOR_VERSION");
            string patch = Macro(text, "ZED_SDK_PATCH_VERSION");
            if (major == null || minor == null || patch == null) return null;
            return major + "." + minor + "." + patch;
        }

        static string Macro(string text, string name)
        {
            Match match = Regex.Match(text, @"^\s*#\s*define\s+" + name + @"\s+([0-9]+)\s*$", RegexOptions.Multiline);
            return match.Success ? match.Groups[1].Value : null;
        }

        static string CmakeValue(string path, string pattern)
        {
            if (!File.Exists(path)) return null;
            Match match = Regex.Match(File.ReadAllText(path), pattern, RegexOptions.IgnoreCase);
            return match.Success ? match.Groups[1].Value : null;
        }

        static List<string> SdkMissing(string directory, string[] names)
        {
            var missing = new List<string>();
            foreach (string name in names)
                if (!File.Exists(Path.Combine(directory, name))) missing.Add(name);
            return missing;
        }

        static bool OnPath(string directory)
        {
            string wanted = Normalize(directory);
            var entries = new List<string>();
            string process = Environment.GetEnvironmentVariable("PATH") ?? "";
            entries.AddRange(process.Split(';'));
            try
            {
                using (var key = RegistryKey.OpenBaseKey(RegistryHive.LocalMachine, RegistryView.Registry64)
                           .OpenSubKey(@"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"))
                {
                    if (key != null) entries.AddRange(Convert.ToString(key.GetValue("Path") ?? "").Split(';'));
                }
            }
            catch (Exception) { }
            foreach (string entry in entries)
            {
                if (entry.Trim().Length == 0) continue;
                if (Normalize(Environment.ExpandEnvironmentVariables(entry)) == wanted) return true;
            }
            return false;
        }

        static string Normalize(string path)
        {
            return path.Trim().Trim('"').TrimEnd('\\').ToLowerInvariant();
        }

        static void GatherGpu(Dictionary<string, object> facts)
        {
            var gpus = new List<object>();
            string driver = null;
            using (var searcher = new ManagementObjectSearcher(
                       "SELECT Name, AdapterCompatibility, DriverVersion FROM Win32_VideoController"))
            {
                foreach (ManagementObject item in searcher.Get())
                {
                    string name = Convert.ToString(item["Name"]);
                    string vendor = Convert.ToString(item["AdapterCompatibility"]);
                    string wmi = Convert.ToString(item["DriverVersion"]);
                    bool nvidia = (name + " " + vendor).IndexOf("NVIDIA", StringComparison.OrdinalIgnoreCase) >= 0;
                    gpus.Add(new Dictionary<string, object>
                    {
                        { "name", name }, { "vendor", vendor }, { "driver_wmi", wmi }, { "nvidia", nvidia },
                    });
                    if (nvidia && driver == null) driver = NvidiaVersion(wmi);
                }
            }
            facts["gpus"] = gpus;
            facts["nvidia_driver"] = driver;
            facts["nvidia_smi_driver"] = NvidiaSmiDriver();
        }

        // Windows reports an NVIDIA driver as e.g. 32.0.16.1656; NVIDIA's own
        // number is the last five digits of the last two fields: 616.56.
        public static string NvidiaVersion(string wmi)
        {
            if (string.IsNullOrEmpty(wmi)) return null;
            string[] parts = wmi.Split('.');
            if (parts.Length != 4) return null;
            string digits = parts[2] + parts[3].PadLeft(4, '0');
            if (digits.Length < 5 || !digits.All(char.IsDigit)) return null;
            digits = digits.Substring(digits.Length - 5);
            return int.Parse(digits.Substring(0, 3), CultureInfo.InvariantCulture).ToString(CultureInfo.InvariantCulture)
                   + "." + digits.Substring(3);
        }

        static string NvidiaSmiDriver()
        {
            string exe = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System), "nvidia-smi.exe");
            if (!File.Exists(exe)) return null;
            try
            {
                var info = new ProcessStartInfo(exe, "--query-gpu=driver_version --format=csv,noheader")
                {
                    UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true,
                    RedirectStandardError = true,
                };
                using (Process process = Process.Start(info))
                {
                    string output = process.StandardOutput.ReadToEnd();
                    process.StandardError.ReadToEnd();
                    if (!process.WaitForExit(15000)) { try { process.Kill(); } catch (Exception) { } return null; }
                    string first = output.Split('\n')[0].Trim();
                    return first.Length > 0 ? first : null;
                }
            }
            catch (Exception) { return null; }
        }

        static string VcRedistVersion()
        {
            using (var key = RegistryKey.OpenBaseKey(RegistryHive.LocalMachine, RegistryView.Registry64)
                       .OpenSubKey(@"SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\X64"))
            {
                if (key == null) return null;
                if (Convert.ToInt32(key.GetValue("Installed") ?? 0) != 1) return null;
                return Convert.ToString(key.GetValue("Version"));
            }
        }

        static void GatherDisk(Dictionary<string, object> facts, string target)
        {
            facts["target_dir"] = target;
            string root = Path.GetPathRoot(Path.GetFullPath(target));
            facts["target_free_bytes"] = new DriveInfo(root).AvailableFreeSpace;
        }

        // ---------------------------------------------------------- evaluate
        public static List<Check> Evaluate(Dictionary<string, object> facts, Requirements needs)
        {
            var checks = new List<Check>();

            long major = Json.Long(facts, "os_major", 0), build = Json.Long(facts, "os_build", 0);
            bool x64 = Json.Bool(facts, "os_64bit", false);
            string osName = major == 10 ? (build >= 22000 ? "Windows 11" : "Windows 10") : ("Windows " + major);
            checks.Add(new Check
            {
                Id = "os", Title = "İşletim sistemi",
                Ok = major == 10 && build >= 10240 && x64,
                Found = osName + " (derleme " + build + (x64 ? ", 64 bit)" : ", 32 bit)"),
                Needed = "Windows 10 veya 11, 64 bit",
                Remedy = "KineCapture yalnız 64 bit Windows 10/11 üzerinde çalışır.",
            });

            string root = Json.Str(facts, "zed_root");
            string header = Json.Str(facts, "zed_header_version");
            string cmake = Json.Str(facts, "zed_cmake_version");
            string registry = Json.Str(facts, "zed_registry_version");
            var zed = new Check
            {
                Id = "zed_sdk", Title = "ZED SDK sürümü", Needed = "birebir " + needs.ZedSdk,
                Remedy = "Stereolabs'ın sitesinden ZED SDK " + needs.ZedSdk + " indirip kurun; başka bir sürüm "
                         + "kuruluysa önce onu kaldırın. Kurulumdan sonra bu kurucuyu yeniden çalıştırın.",
            };
            if (root == null)
            {
                zed.Found = "bulunamadı (ZED_SDK_ROOT_DIR, kayıt defteri ve " + DefaultSdkRoot + " denendi)";
            }
            else if (header == null)
            {
                zed.Found = "sürüm okunamadı (" + root + "\\include\\sl\\Camera.hpp yok ya da bozuk)";
            }
            else
            {
                var seen = new List<string> { "Camera.hpp: " + header };
                if (cmake != null) seen.Add("zed-config-version.cmake: " + cmake);
                if (registry != null) seen.Add("kayıt defteri: " + registry);
                bool consistent = (cmake == null || cmake == header) && (registry == null || registry == header);
                zed.Ok = consistent && header == needs.ZedSdk;
                zed.Found = header + " (" + root + "; " + string.Join(", ", seen) + ")";
                if (!consistent)
                {
                    zed.Found = "tutarsız kurulum: " + string.Join(", ", seen);
                    zed.Remedy = "ZED SDK kurulumu tutarsız görünüyor; ZED SDK " + needs.ZedSdk + "'i kaldırıp yeniden kurun.";
                }
            }
            checks.Add(zed);

            var dlls = Json.Strings(facts, "zed_dlls_missing");
            checks.Add(new Check
            {
                Id = "zed_dlls", Title = "ZED SDK kitaplıkları",
                Ok = root != null && dlls.Count == 0 && facts.ContainsKey("zed_dlls_missing"),
                Found = root == null ? "SDK yok" : (dlls.Count == 0 ? "tamam" : "eksik: " + string.Join(", ", dlls)),
                Needed = string.Join(", ", SdkDlls),
                Remedy = "ZED SDK " + needs.ZedSdk + " kurulumunu onarın ya da yeniden kurun.",
            });

            bool onPath = Json.Bool(facts, "zed_bin_on_path", false);
            checks.Add(new Check
            {
                Id = "zed_path", Title = "ZED SDK klasörü PATH'te",
                Ok = root != null && onPath,
                Found = root == null ? "SDK yok" : (onPath ? "evet" : "hayır"),
                Needed = (Json.Str(facts, "zed_bin") ?? "<ZED SDK>\\bin") + " PATH'te",
                Remedy = "ZED SDK kurulumunu onarın; SDK kurucusu bin klasörünü sistem PATH'ine ekler.",
            });

            var gpuNames = new List<string>();
            bool nvidia = false;
            object gpusValue;
            if (facts.TryGetValue("gpus", out gpusValue) && gpusValue is IEnumerable)
            {
                foreach (object item in (IEnumerable)gpusValue)
                {
                    var gpu = item as Dictionary<string, object>;
                    if (gpu == null) continue;
                    gpuNames.Add(Json.Str(gpu, "name") ?? "?");
                    if (Json.Bool(gpu, "nvidia", false)) nvidia = true;
                }
            }
            checks.Add(new Check
            {
                Id = "gpu", Title = "NVIDIA ekran kartı", Ok = nvidia,
                Found = gpuNames.Count == 0 ? "ekran kartı bulunamadı" : string.Join("; ", gpuNames),
                Needed = "NVIDIA GPU (ZED SDK derinlik ve iskelet takibi için CUDA kullanır)",
                Remedy = "Bu bilgisayarda NVIDIA ekran kartı yok; KineCapture'ın ZED kamerası ile çalışması için gerekir.",
            });

            // The installed SDK says which CUDA it was built with; without an
            // SDK to ask, the release's own build (CUDA 13 for 5.4.1) decides.
            long cuda = Json.Long(facts, "zed_cuda_major", -1);
            if (cuda <= 0) cuda = needs.CudaMajor;
            string minimum = null;
            if (cuda > 0 && Requirements.MinDriverByCuda.ContainsKey((int)cuda)) minimum = Requirements.MinDriverByCuda[(int)cuda];
            string driver = Json.Str(facts, "nvidia_driver") ?? Json.Str(facts, "nvidia_smi_driver");
            var driverCheck = new Check
            {
                Id = "driver", Title = "NVIDIA sürücüsü",
                Found = driver ?? "bulunamadı",
                Needed = minimum == null
                    ? (cuda > 0 ? "CUDA " + cuda + " için alt sınır tanımlı değil" : "ZED SDK'nın CUDA sürümü okunamadı")
                    : "≥ " + minimum + " (ZED SDK CUDA " + cuda + " ile derlenmiş)",
                Remedy = minimum == null
                    ? "ZED SDK'nın hangi CUDA ile derlendiği okunamadı; SDK kurulumunu kontrol edin."
                    : "NVIDIA sürücüsünü güncelleyin (en az " + minimum + ").",
            };
            driverCheck.Ok = nvidia && minimum != null && driver != null && CompareVersions(driver, minimum) >= 0;
            checks.Add(driverCheck);

            var driverDlls = Json.Strings(facts, "driver_dlls_missing");
            checks.Add(new Check
            {
                Id = "cuda_runtime", Title = "CUDA çalışma zamanı (sürücü bileşenleri)",
                Ok = facts.ContainsKey("driver_dlls_missing") && driverDlls.Count == 0,
                Found = !facts.ContainsKey("driver_dlls_missing") ? "denetlenemedi"
                    : (driverDlls.Count == 0 ? "tamam" : "eksik: " + string.Join(", ", driverDlls)),
                Needed = string.Join(", ", DriverDlls) + " (System32)",
                Remedy = "NVIDIA sürücüsünü yeniden kurun; bu dosyalar sürücüyle gelir.",
            });

            var vc = Json.Strings(facts, "vc_dlls_missing");
            checks.Add(new Check
            {
                Id = "vcredist", Title = "Visual C++ çalışma zamanı",
                Ok = facts.ContainsKey("vc_dlls_missing") && vc.Count == 0,
                Found = !facts.ContainsKey("vc_dlls_missing") ? "denetlenemedi"
                    : (vc.Count == 0 ? "tamam" + (Json.Str(facts, "vc_redist_version") != null ? " (" + Json.Str(facts, "vc_redist_version") + ")" : "")
                                     : "eksik: " + string.Join(", ", vc)),
                Needed = string.Join(", ", VcDlls),
                Remedy = "Microsoft Visual C++ 2015-2022 Redistributable (x64) kurun (ZED SDK kurucusu da kurar).",
            });

            string target = Json.Str(facts, "target_dir") ?? "";
            long free = Json.Long(facts, "target_free_bytes", -1);
            checks.Add(new Check
            {
                Id = "disk", Title = "Disk alanı",
                Ok = free >= 0 && free >= needs.RequiredBytes,
                Found = free < 0 ? "okunamadı" : Gb(free) + " boş",
                Needed = Gb(needs.RequiredBytes) + " (" + target + ")",
                Remedy = "Hedef sürücüde yer açın ya da başka bir kurulum klasörü seçin.",
            });

            int longest = target.TrimEnd('\\').Length + 1 + needs.MaxRelativePath;
            checks.Add(new Check
            {
                Id = "path_length", Title = "Kurulum yolu uzunluğu",
                Ok = needs.MaxRelativePath == 0 || longest <= MaxPath,
                Found = "en uzun dosya yolu " + longest + " karakter",
                Needed = "≤ " + MaxPath + " karakter (Windows yol sınırı)",
                Remedy = "Daha kısa bir kurulum klasörü seçin (örneğin C:\\KineCapture).",
            });
            return checks;
        }

        public static int CompareVersions(string a, string b)
        {
            string[] x = a.Split('.'), y = b.Split('.');
            for (int i = 0; i < Math.Max(x.Length, y.Length); i++)
            {
                int p = i < x.Length ? ParseInt(x[i]) : 0, q = i < y.Length ? ParseInt(y[i]) : 0;
                if (p != q) return p.CompareTo(q);
            }
            return 0;
        }

        static int ParseInt(string text)
        {
            int value;
            return int.TryParse(new string(text.TakeWhile(char.IsDigit).ToArray()), NumberStyles.Integer,
                CultureInfo.InvariantCulture, out value) ? value : 0;
        }

        public static string Gb(long bytes)
        {
            return (bytes / 1073741824.0).ToString("0.0", CultureInfo.InvariantCulture) + " GB";
        }

        public static string Describe(List<Check> checks)
        {
            var text = new StringBuilder();
            foreach (Check check in checks)
            {
                text.AppendLine((check.Ok ? "[ TAMAM ] " : "[ EKSİK ] ") + check.Title + ": " + check.Found);
                if (!check.Ok)
                {
                    text.AppendLine("           Gereken: " + check.Needed);
                    text.AppendLine("           Yapılacak: " + check.Remedy);
                }
            }
            return text.ToString();
        }
    }

    // ============================================================ installing
    sealed class StepFailed : Exception
    {
        public StepFailed(string message) : base(message) { }
    }

    sealed class Installer
    {
        // Folders deeper than 247 characters cannot be created without the
        // extended prefix even when every file in them is within MAX_PATH.
        public static string Long(string path)
        {
            if (path.StartsWith(@"\\?\", StringComparison.Ordinal) || path.Length < 240) return path;
            if (path.StartsWith(@"\\", StringComparison.Ordinal)) return @"\\?\UNC\" + path.Substring(2);
            return @"\\?\" + path;
        }

        public const string Marker = "kinecapture-install.json";
        public const string FileList = "kinecapture-files.txt";
        public const string Uninstaller = "uninstall.exe";
        public const string InstallLog = "install.log";

        readonly Payload payload;
        readonly Options options;
        readonly Log log;
        public Action<int, string> Progress = delegate { };
        public List<string> VerifyLines = new List<string>();

        public Installer(Payload payload, Options options, Log log)
        {
            this.payload = payload; this.options = options; this.log = log;
        }

        void Report(int percent, string text)
        {
            log.Info(text);
            Progress(percent, text);
        }

        public int Install(string target)
        {
            target = Path.GetFullPath(target).TrimEnd('\\');
            Report(0, "Kurulum klasörü: " + target);
            Dictionary<string, object> old;
            string previous = PrepareTarget(target, out old);
            var written = new List<string>();
            bool success = false;
            try
            {
                Extract(target, written);
                string stub = Path.Combine(target, Uninstaller);
                payload.WriteStub(stub);
                written.Add(Uninstaller);
                WriteMarker(target, written, previous);
                RunSteps(target, "post_install", 55, 85);
                success = Verify(target);
                if (!success) throw new StepFailed("Kurulum sonrası doğrulama geçmedi.");
                var shortcuts = options.NoShortcuts ? new List<string>() : CreateShortcuts(target);
                Register(target, shortcuts);
                WriteMarker(target, written, previous, shortcuts);
                Report(100, "Kurulum tamamlandı.");
                try { log.CopyTo(Path.Combine(target, InstallLog)); } catch (Exception) { }
                return ExitCode.Ok;
            }
            catch (Exception exc)
            {
                success = false;
                log.Error("Kurulum başarısız: " + exc.Message);
                Report(100, "Kurulum geri alınıyor...");
                RollBack(target);
                // A failed reinstall leaves nothing to start; the previous
                // installation's shortcuts and entry must not point at it.
                if (old != null) Uninstall.ForgetRegistration(old, options.RegKey, log);
                throw;
            }
            finally
            {
                if (!success) TryDeleteEmpty(target);
            }
        }

        // A reinstall over our own installation replaces the program files;
        // anything else in a non-empty folder is refused rather than mixed in.
        string PrepareTarget(string target, out Dictionary<string, object> old)
        {
            old = null;
            if (!Directory.Exists(target)) return null;
            string marker = Path.Combine(target, Marker);
            if (File.Exists(marker))
            {
                old = Json.ParseObject(File.ReadAllText(marker, Encoding.UTF8));
                Report(1, "Önceki kurulum bulundu (" + (Json.Str(old, "version") ?? "?") + "); program dosyaları değiştirilecek, veriler korunur.");
                RemoveProgramFiles(target, log, false);
                return Json.Str(old, "version");
            }
            if (Directory.EnumerateFileSystemEntries(target).Any())
                throw new StepFailed("Kurulum klasörü boş değil ve bir KineCapture kurulumu değil: " + target
                                     + ". Boş ya da yeni bir klasör seçin.");
            return null;
        }

        void Extract(string target, List<string> written)
        {
            var entries = payload.Archive.Entries.Where(e => e.FullName.StartsWith("env/", StringComparison.Ordinal)).ToList();
            long total = Math.Max(1, entries.Sum(e => e.Length)), done = 0;
            int lastPercent = -1;
            string root = target + "\\";
            var buffer = new byte[1 << 20];
            Directory.CreateDirectory(target);
            foreach (ZipArchiveEntry entry in entries)
            {
                string relative = entry.FullName.Replace('/', '\\');
                string destination = Path.GetFullPath(Path.Combine(target, relative));
                if (!destination.StartsWith(root, StringComparison.OrdinalIgnoreCase))
                    throw new StepFailed("Kurulum yükünde klasör dışına çıkan bir yol var: " + entry.FullName);
                if (entry.FullName.EndsWith("/", StringComparison.Ordinal))
                {
                    Directory.CreateDirectory(Long(destination));
                    continue;
                }
                Directory.CreateDirectory(Long(Path.GetDirectoryName(destination)));
                using (Stream input = entry.Open())
                using (var output = new FileStream(Long(destination), FileMode.Create, FileAccess.Write, FileShare.None, 1 << 16))
                {
                    int read;
                    while ((read = input.Read(buffer, 0, buffer.Length)) > 0) output.Write(buffer, 0, read);
                }
                written.Add(relative);
                done += entry.Length;
                int percent = 2 + (int)(50.0 * done / total);
                if (percent != lastPercent)
                {
                    lastPercent = percent;
                    Progress(percent, "Dosyalar açılıyor... " + written.Count + " / " + entries.Count);
                }
            }
            log.Info(written.Count + " dosya açıldı.");
        }

        void WriteMarker(string target, List<string> written, string previous, List<string> shortcuts = null)
        {
            File.WriteAllLines(Path.Combine(target, FileList), written, new UTF8Encoding(false));
            var marker = new Dictionary<string, object>
            {
                { "product", payload.Product },
                { "version", payload.Version },
                { "installed_at", DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ", CultureInfo.InvariantCulture) },
                { "previous_version", previous },
                { "registry_key", options.RegKey },
                { "shortcuts", shortcuts ?? new List<string>() },
                { "launch", Json.Str(payload.Install, "launch_exe") },
            };
            File.WriteAllText(Path.Combine(target, Marker), Json.Write(marker), new UTF8Encoding(false));
        }

        // Steps come from the payload's own install.json, so the installer is
        // the same program for every release: conda-unpack, module compiling.
        void RunSteps(string target, string key, int from, int to)
        {
            object value;
            if (!payload.Install.TryGetValue(key, out value) || !(value is IEnumerable)) return;
            var steps = ((IEnumerable)value).Cast<object>().OfType<Dictionary<string, object>>().ToList();
            for (int i = 0; i < steps.Count; i++)
            {
                var step = steps[i];
                string title = Json.Str(step, "title") ?? "Adım";
                Report(from + (to - from) * i / Math.Max(1, steps.Count), title + "...");
                int code = RunTool(target, step, null);
                if (code != 0) throw new StepFailed(title + " başarısız (çıkış kodu " + code + "). Ayrıntı: " + log.FilePath);
            }
        }

        int RunTool(string target, Dictionary<string, object> step, string report)
        {
            string exe = Path.Combine(target, (Json.Str(step, "exe") ?? "").Replace('/', '\\'));
            string args = (Json.Str(step, "args") ?? "").Replace("{target}", target).Replace("{report}", report ?? "");
            string cwd = Path.Combine(target, (Json.Str(step, "cwd") ?? "").Replace('/', '\\'));
            int timeout = (int)Json.Long(step, "timeout_s", 900) * 1000;
            if (!File.Exists(exe)) throw new StepFailed("Çalıştırılacak dosya yok: " + exe);
            log.Info("Çalıştırılıyor: \"" + exe + "\" " + args);
            var info = new ProcessStartInfo(exe, args)
            {
                UseShellExecute = false, CreateNoWindow = true, WorkingDirectory = cwd,
                RedirectStandardOutput = true, RedirectStandardError = true,
                StandardOutputEncoding = Encoding.UTF8, StandardErrorEncoding = Encoding.UTF8,
            };
            // A child of an installer must not write bytecode into places the
            // step did not ask for, nor pick up the builder's Python settings.
            info.EnvironmentVariables.Remove("PYTHONPATH");
            info.EnvironmentVariables.Remove("PYTHONHOME");
            info.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";
            var watch = Stopwatch.StartNew();
            using (var process = new Process { StartInfo = info })
            {
                process.OutputDataReceived += (s, e) => { if (e.Data != null && e.Data.Trim().Length > 0) log.Info("  " + e.Data); };
                process.ErrorDataReceived += (s, e) => { if (e.Data != null && e.Data.Trim().Length > 0) log.Warn("  " + e.Data); };
                process.Start();
                process.BeginOutputReadLine();
                process.BeginErrorReadLine();
                if (!process.WaitForExit(timeout))
                {
                    try { process.Kill(); } catch (Exception) { }
                    throw new StepFailed(Path.GetFileName(exe) + " zaman aşımına uğradı (" + timeout / 1000 + " s).");
                }
                process.WaitForExit();
                log.Info("  çıkış kodu " + process.ExitCode + ", " + watch.Elapsed.TotalSeconds.ToString("0.0", CultureInfo.InvariantCulture) + " s");
                return process.ExitCode;
            }
        }

        int RunDetached(string target, Dictionary<string, object> step, string report)
        {
            string exe = Path.Combine(target, (Json.Str(step, "exe") ?? "").Replace('/', '\\'));
            string args = (Json.Str(step, "args") ?? "").Replace("{target}", target).Replace("{report}", report ?? "");
            string cwd = Path.Combine(target, (Json.Str(step, "cwd") ?? "").Replace('/', '\\'));
            int timeout = (int)Json.Long(step, "timeout_s", 900) * 1000;
            if (!File.Exists(exe)) throw new StepFailed("Çalıştırılacak dosya yok: " + exe);
            var environment = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            foreach (DictionaryEntry pair in Environment.GetEnvironmentVariables())
                environment[(string)pair.Key] = (string)pair.Value;
            environment.Remove("PYTHONPATH");
            environment.Remove("PYTHONHOME");
            log.Info("Çalıştırılıyor (konsolsuz, standart tanıtıcısız): \"" + exe + "\" " + args);
            var watch = Stopwatch.StartNew();
            int code = Detached.Run(exe, args, cwd, environment, timeout);
            log.Info("  çıkış kodu " + code + ", " + watch.Elapsed.TotalSeconds.ToString("0.0", CultureInfo.InvariantCulture) + " s");
            return code;
        }

        bool Verify(string target)
        {
            object value;
            if (!payload.Install.TryGetValue("verify", out value) || !(value is IEnumerable)) return true;
            bool ok = true;
            foreach (var step in ((IEnumerable)value).Cast<object>().OfType<Dictionary<string, object>>())
            {
                string title = Json.Str(step, "title") ?? "Doğrulama";
                Report(88, title + "...");
                string report = Path.Combine(Places.Temp, "KineCapture-selfcheck-" + Guid.NewGuid().ToString("N") + ".json");
                int code = RunDetached(target, step, report);
                bool wantsReport = (Json.Str(step, "args") ?? "").Contains("{report}");
                if (!wantsReport)
                {
                    VerifyLines.Add((code == 0 ? "[ TAMAM ] " : "[ EKSİK ] ") + title + " (çıkış kodu " + code + ")");
                }
                else if (File.Exists(report))
                {
                    string text = File.ReadAllText(report, Encoding.UTF8);
                    log.Info("Öz-denetim raporu: " + text);
                    try
                    {
                        var parsed = Json.ParseObject(text);
                        VerifyLines.AddRange(SelfCheckLines(parsed));
                        if (Json.Bool(parsed, "console", true))
                        {
                            VerifyLines.Add("[ EKSİK ] Öz-denetim konsol ile çalıştı; konsolsuz başlatıcı bekleniyordu.");
                            ok = false;
                        }
                    }
                    catch (Exception exc) { log.Warn("Rapor okunamadı: " + exc.Message); }
                    try { File.Delete(report); } catch (Exception) { }
                }
                else
                {
                    // A self-check that wrote no report did not run to its end,
                    // whatever its exit code says.
                    VerifyLines.Add("[ EKSİK ] " + title + ": rapor üretilmedi.");
                    ok = false;
                }
                if (code != 0) ok = false;
            }
            return ok;
        }

        static IEnumerable<string> SelfCheckLines(Dictionary<string, object> report)
        {
            object value;
            if (!report.TryGetValue("checks", out value)) yield break;
            var checks = value as Dictionary<string, object>;
            if (checks == null) yield break;
            foreach (var pair in checks)
            {
                var check = pair.Value as Dictionary<string, object>;
                if (check == null) continue;
                bool ok = Json.Bool(check, "ok", false), required = Json.Bool(check, "required", true);
                yield return (ok ? "[ TAMAM ] " : required ? "[ EKSİK ] " : "[  not  ] ") + pair.Key + ": " + Json.Str(check, "detail");
            }
        }

        List<string> CreateShortcuts(string target)
        {
            var made = new List<string>();
            string exe = Path.Combine(target, (Json.Str(payload.Install, "launch_exe") ?? @"env\pythonw.exe").Replace('/', '\\'));
            string args = Json.Str(payload.Install, "launch_args") ?? "-B -m kinecapture";
            string icon = Json.Str(payload.Install, "icon");
            icon = icon == null ? exe : Path.Combine(target, icon.Replace('/', '\\'));
            string home = Environment.GetEnvironmentVariable("USERPROFILE") ?? target;
            var places = new List<string> { Path.Combine(Places.StartMenuDir, "KineCapture.lnk") };
            if (!options.NoDesktop) places.Add(Path.Combine(Places.Desktop, "KineCapture.lnk"));
            foreach (string link in places)
            {
                try
                {
                    Directory.CreateDirectory(Path.GetDirectoryName(link));
                    Type shellType = Type.GetTypeFromProgID("WScript.Shell");
                    dynamic shell = Activator.CreateInstance(shellType);
                    dynamic shortcut = shell.CreateShortcut(link);
                    shortcut.TargetPath = exe;
                    shortcut.Arguments = args;
                    shortcut.WorkingDirectory = home;
                    shortcut.IconLocation = icon + ",0";
                    shortcut.Description = "KineCapture Studio";
                    shortcut.Save();
                    made.Add(link);
                    log.Info("Kısayol: " + link);
                }
                catch (Exception exc) { log.Warn("Kısayol oluşturulamadı (" + link + "): " + exc.Message); }
            }
            return made;
        }

        void Register(string target, List<string> shortcuts)
        {
            string path = @"Software\Microsoft\Windows\CurrentVersion\Uninstall\" + options.RegKey;
            using (RegistryKey key = Registry.CurrentUser.CreateSubKey(path))
            {
                string uninstall = "\"" + Path.Combine(target, Uninstaller) + "\" /uninstall";
                key.SetValue("DisplayName", "KineCapture");
                key.SetValue("DisplayVersion", payload.Version);
                key.SetValue("Publisher", "KineCapture");
                key.SetValue("InstallLocation", target);
                key.SetValue("UninstallString", uninstall);
                key.SetValue("QuietUninstallString", uninstall + " /silent");
                key.SetValue("DisplayIcon", Path.Combine(target, Uninstaller));
                key.SetValue("NoModify", 1, RegistryValueKind.DWord);
                key.SetValue("NoRepair", 1, RegistryValueKind.DWord);
                key.SetValue("InstallDate", DateTime.Now.ToString("yyyyMMdd", CultureInfo.InvariantCulture));
                long kb = Json.Long(payload.Install, "unpacked_bytes", 0) / 1024;
                key.SetValue("EstimatedSize", (int)Math.Min(int.MaxValue, kb), RegistryValueKind.DWord);
            }
            log.Info("Kaldırma kaydı: HKCU\\" + path);
        }

        void RollBack(string target)
        {
            try { RemoveProgramFiles(target, log, true); }
            catch (Exception exc) { log.Error("Geri alma tamamlanamadı: " + exc.Message); }
        }

        // Program files only: env\, the uninstaller and the installer's own
        // bookkeeping. Data never lives here, and a file the user put in the
        // folder is left where it is.
        public static void RemoveProgramFiles(string target, Log log, bool includeUninstaller)
        {
            string env = Path.Combine(target, "env");
            if (Directory.Exists(env)) DeleteTree(env, log);
            foreach (string name in new[] { Marker, FileList, InstallLog })
            {
                string file = Path.Combine(target, name);
                if (File.Exists(file)) File.Delete(file);
            }
            if (includeUninstaller)
            {
                string file = Path.Combine(target, Uninstaller);
                if (File.Exists(file)) File.Delete(file);
            }
        }

        static void DeleteTree(string directory, Log log)
        {
            // Read-only attributes (conda sets a few) would stop a plain delete.
            foreach (string file in Directory.EnumerateFiles(directory, "*", SearchOption.AllDirectories))
            {
                try { File.SetAttributes(file, FileAttributes.Normal); } catch (Exception) { }
            }
            for (int attempt = 0; ; attempt++)
            {
                try { Directory.Delete(Long(directory), true); return; }
                catch (IOException)
                {
                    if (attempt >= 5) throw;
                    Thread.Sleep(500);
                }
                catch (UnauthorizedAccessException)
                {
                    if (attempt >= 5) throw;
                    Thread.Sleep(500);
                }
            }
        }

        public static void TryDeleteEmpty(string directory)
        {
            try
            {
                if (Directory.Exists(directory) && !Directory.EnumerateFileSystemEntries(directory).Any())
                    Directory.Delete(directory);
            }
            catch (Exception) { }
        }
    }

    // ========================================================== uninstalling
    static class Uninstall
    {
        public static int Run(Options options, Log log, Func<string, bool> confirm)
        {
            string target = options.Dir ?? Path.GetDirectoryName(Application.ExecutablePath);
            target = Path.GetFullPath(target).TrimEnd('\\');
            string markerPath = Path.Combine(target, Installer.Marker);
            if (!File.Exists(markerPath))
            {
                log.Error("Burada bir KineCapture kurulumu yok: " + target);
                return ExitCode.Usage;
            }
            var marker = Json.ParseObject(File.ReadAllText(markerPath, Encoding.UTF8));
            if (Json.Str(marker, "product") != "KineCapture")
            {
                log.Error("Kurulum işareti KineCapture'a ait değil: " + markerPath);
                return ExitCode.Usage;
            }
            if (!confirm("KineCapture " + (Json.Str(marker, "version") ?? "") + " kaldırılsın mı?\n\n"
                         + "Yalnız program dosyaları silinir. Veri setleri, hesaplar (kimlik veritabanı) ve "
                         + "loglar olduğu gibi kalır.\n\n" + target))
            {
                log.Info("Kaldırma iptal edildi.");
                return ExitCode.Cancelled;
            }
            ForgetRegistration(marker, options.RegKey, log);
            Installer.RemoveProgramFiles(target, log, false);
            log.Info("Program dosyaları silindi: " + target);
            ScheduleSelfDelete(target, log);
            return ExitCode.Ok;
        }

        public static void ForgetRegistration(Dictionary<string, object> marker, string fallbackKey, Log log)
        {
            foreach (string link in Json.Strings(marker, "shortcuts"))
            {
                try { if (File.Exists(link)) File.Delete(link); log.Info("Kısayol silindi: " + link); }
                catch (Exception exc) { log.Warn("Kısayol silinemedi (" + link + "): " + exc.Message); }
            }
            string regKey = Json.Str(marker, "registry_key") ?? fallbackKey;
            try
            {
                Registry.CurrentUser.DeleteSubKeyTree(@"Software\Microsoft\Windows\CurrentVersion\Uninstall\" + regKey, false);
                log.Info("Kaldırma kaydı silindi: " + regKey);
            }
            catch (Exception exc) { log.Warn("Kaldırma kaydı silinemedi: " + exc.Message); }
        }

        // The running uninstaller cannot delete itself; a hidden cmd does it a
        // moment after this process exits, and removes the folder only if it
        // is empty (rmdir without /s) - a file the user left there stays.
        static void ScheduleSelfDelete(string target, Log log)
        {
            string self = Path.Combine(target, Installer.Uninstaller);
            string command = "/d /c ping -n 3 127.0.0.1 >nul & del /f /q \"" + self + "\" & rmdir \"" + target + "\"";
            try
            {
                var info = new ProcessStartInfo(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System), "cmd.exe"), command)
                {
                    UseShellExecute = false, CreateNoWindow = true, WorkingDirectory = Places.Temp,
                };
                Process.Start(info);
            }
            catch (Exception exc) { log.Warn("Kaldırıcı kendini silemedi: " + exc.Message); }
        }
    }

    // ==================================================================== UI
    sealed class SetupForm : Form
    {
        readonly Payload payload;
        readonly Options options;
        readonly Log log;
        readonly TextBox results = new TextBox();
        readonly TextBox folder = new TextBox();
        readonly Button browse = new Button();
        readonly CheckBox desktop = new CheckBox();
        readonly ProgressBar progress = new ProgressBar();
        readonly Label status = new Label();
        readonly Button install = new Button();
        readonly Button close = new Button();
        Requirements needs;
        bool preflightOk, busy, installing;
        public int Result = ExitCode.Cancelled;

        public SetupForm(Payload payload, Options options, Log log)
        {
            this.payload = payload; this.options = options; this.log = log;
            needs = Requirements.From(payload.Install);
            Text = "KineCapture " + payload.Version + " Kurulumu";
            Font = new Font("Segoe UI", 9.5f);
            ClientSize = new Size(760, 560);
            MinimumSize = new Size(640, 480);
            StartPosition = FormStartPosition.CenterScreen;
            try { Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath); } catch (Exception) { }

            var heading = new Label
            {
                Text = "KineCapture " + payload.Version + " kurulumu",
                Font = new Font("Segoe UI Semibold", 13f), AutoSize = true, Location = new Point(16, 14),
            };
            var intro = new Label
            {
                Text = "Önce bu bilgisayarın KineCapture'ı çalıştırıp çalıştıramayacağı denetlenir. Eksik varsa "
                       + "hiçbir şey kurulmaz.",
                AutoSize = false, Location = new Point(16, 46), Size = new Size(728, 36),
                Anchor = AnchorStyles.Top | AnchorStyles.Left | AnchorStyles.Right,
            };
            results.Multiline = true; results.ReadOnly = true; results.ScrollBars = ScrollBars.Vertical;
            results.Font = new Font("Consolas", 9f); results.WordWrap = true;
            results.Location = new Point(16, 86); results.Size = new Size(728, 300);
            results.Anchor = AnchorStyles.Top | AnchorStyles.Bottom | AnchorStyles.Left | AnchorStyles.Right;
            var folderLabel = new Label
            {
                Text = "Kurulum klasörü:", AutoSize = true, Location = new Point(16, 400),
                Anchor = AnchorStyles.Bottom | AnchorStyles.Left,
            };
            folder.Text = options.Dir ?? Places.DefaultTarget;
            folder.Location = new Point(130, 396); folder.Size = new Size(520, 26);
            folder.Anchor = AnchorStyles.Bottom | AnchorStyles.Left | AnchorStyles.Right;
            browse.Text = "Gözat..."; browse.Location = new Point(660, 394); browse.Size = new Size(84, 28);
            browse.Anchor = AnchorStyles.Bottom | AnchorStyles.Right;
            browse.Click += delegate { Browse(); };
            desktop.Text = "Masaüstüne kısayol oluştur"; desktop.Checked = !options.NoDesktop;
            desktop.Location = new Point(130, 426); desktop.AutoSize = true;
            desktop.Anchor = AnchorStyles.Bottom | AnchorStyles.Left;
            progress.Location = new Point(16, 460); progress.Size = new Size(728, 18);
            progress.Anchor = AnchorStyles.Bottom | AnchorStyles.Left | AnchorStyles.Right;
            status.Location = new Point(16, 484); status.Size = new Size(728, 22); status.AutoEllipsis = true;
            status.Anchor = AnchorStyles.Bottom | AnchorStyles.Left | AnchorStyles.Right;
            install.Text = "Kur"; install.Enabled = false; install.Size = new Size(110, 32);
            install.Location = new Point(518, 516); install.Anchor = AnchorStyles.Bottom | AnchorStyles.Right;
            install.Click += delegate { StartInstall(); };
            close.Text = "Kapat"; close.Size = new Size(110, 32);
            close.Location = new Point(634, 516); close.Anchor = AnchorStyles.Bottom | AnchorStyles.Right;
            close.Click += delegate { Close(); };
            Controls.AddRange(new Control[] { heading, intro, results, folderLabel, folder, browse, desktop, progress, status, install, close });
            AcceptButton = install; CancelButton = close;
            folder.TextChanged += delegate { if (!busy) install.Enabled = false; };
            folder.Leave += delegate { if (!busy) RunPreflight(); };
            Shown += delegate { RunPreflight(); };
            FormClosing += (s, e) => { if (busy) e.Cancel = true; };
        }

        void Browse()
        {
            using (var dialog = new FolderBrowserDialog())
            {
                dialog.Description = "KineCapture'ın kurulacağı klasörü seçin (boş ya da yeni bir klasör).";
                dialog.SelectedPath = folder.Text;
                if (dialog.ShowDialog(this) == DialogResult.OK)
                {
                    string chosen = dialog.SelectedPath;
                    if (!chosen.TrimEnd('\\').EndsWith("KineCapture", StringComparison.OrdinalIgnoreCase)
                        && Directory.Exists(chosen) && Directory.EnumerateFileSystemEntries(chosen).Any())
                        chosen = Path.Combine(chosen, "KineCapture");
                    folder.Text = chosen;
                    RunPreflight();
                }
            }
        }

        void RunPreflight()
        {
            string target = folder.Text.Trim();
            SetBusy(true, "Bilgisayar denetleniyor...");
            var worker = new Thread(delegate ()
            {
                List<Check> checks;
                try { checks = Program.RunPreflight(options, target, needs, log); }
                catch (Exception exc)
                {
                    log.Error("Ön denetim çalışmadı: " + exc);
                    checks = new List<Check> { new Check { Id = "preflight", Title = "Ön denetim", Found = exc.Message, Needed = "-", Remedy = "Log dosyasına bakın." } };
                }
                BeginInvoke(new Action(delegate
                {
                    preflightOk = checks.All(c => c.Ok);
                    results.Text = Preflight.Describe(checks).Replace("\n", "\r\n") + "\r\n"
                                   + (preflightOk ? "Her şey uygun. Kurmak için \"Kur\"a basın."
                                                  : "Eksikler giderilmeden kurulum yapılamaz. Bu bilgisayarda hiçbir değişiklik yapılmadı.")
                                   + "\r\nLog: " + log.FilePath;
                    SetBusy(false, preflightOk ? "Denetim geçti." : "Denetim geçmedi.");
                    install.Enabled = preflightOk;
                }));
            });
            worker.IsBackground = true;
            worker.Start();
        }

        void StartInstall()
        {
            if (!preflightOk || busy) return;
            string target = folder.Text.Trim();
            options.NoDesktop = !desktop.Checked;
            installing = true;
            SetBusy(true, "Kuruluyor...");
            results.Text = "";
            var installer = new Installer(payload, options, log);
            installer.Progress = (percent, text) => BeginInvoke(new Action(delegate
            {
                progress.Value = Math.Max(0, Math.Min(100, percent));
                status.Text = text;
            }));
            log.Line += Append;
            var worker = new Thread(delegate ()
            {
                string summary;
                try
                {
                    Result = installer.Install(target);
                    summary = "\r\nKurulum tamamlandı. KineCapture'ı Başlat menüsünden açabilirsiniz.\r\n"
                              + "İlk açılışta Sistem Sahibi hesabı oluşturulur (kurulum paketinde hazır hesap varsa giriş ekranı açılır).";
                }
                catch (Exception exc)
                {
                    Result = ExitCode.InstallFailed;
                    summary = "\r\nKurulum tamamlanamadı: " + exc.Message + "\r\nYapılan değişiklikler geri alındı. Log: " + log.FilePath;
                }
                BeginInvoke(new Action(delegate
                {
                    log.Line -= Append;
                    if (installer.VerifyLines.Count > 0)
                        results.AppendText("\r\nKurulum sonrası doğrulama:\r\n" + string.Join("\r\n", installer.VerifyLines) + "\r\n");
                    results.AppendText(summary + "\r\n");
                    SetBusy(false, Result == ExitCode.Ok ? "Kurulum tamamlandı." : "Kurulum başarısız.");
                    install.Enabled = false;
                    close.Text = "Bitir";
                }));
            });
            worker.IsBackground = true;
            worker.Start();
        }

        void Append(string line)
        {
            BeginInvoke(new Action(delegate { results.AppendText(line + "\r\n"); }));
        }

        void SetBusy(bool value, string text)
        {
            busy = value;
            status.Text = text;
            browse.Enabled = folder.Enabled = desktop.Enabled = !value;
            close.Enabled = !value;
            if (value) install.Enabled = false;
            progress.Style = value && !installing ? ProgressBarStyle.Marquee : ProgressBarStyle.Continuous;
        }
    }

    // =============================================================== program
    static class Program
    {
        public static List<Check> RunPreflight(Options options, string target, Requirements needs, Log log)
        {
            Dictionary<string, object> facts;
            if (!string.IsNullOrEmpty(options.FactsPath))
            {
                facts = Json.ParseObject(File.ReadAllText(options.FactsPath, Encoding.UTF8));
                log.Info("Ön denetim test olgularıyla çalışıyor: " + options.FactsPath);
                if (!facts.ContainsKey("target_dir")) facts["target_dir"] = target;
            }
            else
            {
                facts = Preflight.Gather(options.SdkRoot, target, log);
            }
            log.Info("Olgular: " + Json.Write(facts));
            var checks = Preflight.Evaluate(facts, needs);
            log.Info("Ön denetim:\n" + Preflight.Describe(checks));
            lastFacts = facts;
            return checks;
        }

        static Dictionary<string, object> lastFacts;

        static void WriteReport(Options options, string mode, List<Check> checks, int code, Installer installer)
        {
            if (string.IsNullOrEmpty(options.ReportPath)) return;
            var report = new Dictionary<string, object>
            {
                { "mode", mode }, { "exit_code", code },
                { "ok", checks == null || checks.All(c => c.Ok) },
                { "checks", checks == null ? new List<object>() : checks.Select(c => (object)c.ToMap()).ToList() },
                { "facts", lastFacts },
                { "verify", installer == null ? new List<string>() : installer.VerifyLines },
            };
            Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(options.ReportPath)));
            File.WriteAllText(options.ReportPath, Json.Write(report), new UTF8Encoding(false));
        }

        [STAThread]
        static int Main(string[] args)
        {
            AppContext.SetSwitch("Switch.System.IO.UseLegacyPathHandling", false);
            AppContext.SetSwitch("Switch.System.IO.BlockLongPaths", false);
            Options options;
            try { options = Options.Parse(args); }
            catch (ArgumentException exc)
            {
                bool silent = args.Any(a => a.TrimStart('/', '-').Equals("silent", StringComparison.OrdinalIgnoreCase));
                if (!silent) MessageBox.Show(exc.Message, "KineCapture Kurulum", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return ExitCode.Usage;
            }
            string logPath = options.LogPath ?? Path.Combine(Places.Temp,
                "KineCapture-" + (options.Uninstall ? "Uninstall" : "Setup") + "-"
                + DateTime.Now.ToString("yyyyMMdd-HHmmss", CultureInfo.InvariantCulture) + ".log");
            using (var log = new Log(logPath))
            {
                log.Info("KineCapture kurulum programı başladı: " + string.Join(" ", args));
                try
                {
                    if (options.Uninstall) return Uninstall.Run(options, log, Confirm(options));
                    return RunSetup(options, log);
                }
                catch (Exception exc)
                {
                    log.Error("Beklenmeyen hata: " + exc);
                    if (!options.Silent)
                        MessageBox.Show(exc.Message + "\n\nLog: " + log.FilePath, "KineCapture Kurulum",
                            MessageBoxButtons.OK, MessageBoxIcon.Error);
                    return exc is StepFailed ? ExitCode.InstallFailed : ExitCode.Error;
                }
            }
        }

        static Func<string, bool> Confirm(Options options)
        {
            if (options.Silent) return text => true;
            return text => MessageBox.Show(text, "KineCapture Kaldırma", MessageBoxButtons.YesNo,
                               MessageBoxIcon.Question, MessageBoxDefaultButton.Button2) == DialogResult.Yes;
        }

        static int RunSetup(Options options, Log log)
        {
            Payload payload = Payload.Open(Application.ExecutablePath);
            if (payload == null && !options.CheckOnly
                && Path.GetFileName(Application.ExecutablePath).Equals(Installer.Uninstaller, StringComparison.OrdinalIgnoreCase))
                return Uninstall.Run(options, log, Confirm(options));
            var needs = payload == null ? new Requirements() : Requirements.From(payload.Install);
            string target = Path.GetFullPath(options.Dir ?? Places.DefaultTarget).TrimEnd('\\');
            try
            {
                if (options.CheckOnly || payload == null)
                {
                    if (payload == null && !options.CheckOnly)
                        log.Warn("Bu programda kurulum yükü yok; yalnız denetim yapılıyor.");
                    var checks = RunPreflight(options, target, needs, log);
                    int code = checks.All(c => c.Ok) ? ExitCode.Ok : ExitCode.PreflightFailed;
                    WriteReport(options, "checkonly", checks, code, null);
                    if (!options.Silent)
                        MessageBox.Show(Preflight.Describe(checks) + "\n"
                                        + (code == ExitCode.Ok ? "Bu bilgisayar KineCapture için uygun." : "Eksikler var; hiçbir değişiklik yapılmadı.")
                                        + "\n\nLog: " + log.FilePath, "KineCapture uygunluk denetimi", MessageBoxButtons.OK,
                            code == ExitCode.Ok ? MessageBoxIcon.Information : MessageBoxIcon.Warning);
                    return code;
                }
                if (!options.Silent)
                {
                    Application.EnableVisualStyles();
                    Application.SetCompatibleTextRenderingDefault(false);
                    var form = new SetupForm(payload, options, log);
                    Application.Run(form);
                    return form.Result;
                }
                var preflight = RunPreflight(options, target, needs, log);
                if (!preflight.All(c => c.Ok))
                {
                    log.Error("Ön denetim geçmedi; hiçbir değişiklik yapılmadı.");
                    WriteReport(options, "install", preflight, ExitCode.PreflightFailed, null);
                    return ExitCode.PreflightFailed;
                }
                var installer = new Installer(payload, options, log);
                int result;
                try { result = installer.Install(target); }
                catch (Exception exc)
                {
                    log.Error("Kurulum başarısız: " + exc.Message);
                    result = ExitCode.InstallFailed;
                }
                WriteReport(options, "install", preflight, result, installer);
                return result;
            }
            finally
            {
                if (payload != null) payload.Dispose();
            }
        }
    }
}
