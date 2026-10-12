param([string]$InitialPath, [Parameter(Mandatory=$true)][string]$ResultPath)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;

public static class MobileLibraryFolderPicker {
    [ComImport, Guid("D57C7288-D4AD-4768-BE02-9D969532D960"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IFileOpenDialog {
        [PreserveSig] int Show(IntPtr owner);
        void SetFileTypes(uint count, IntPtr types); void SetFileTypeIndex(uint index); void GetFileTypeIndex(out uint index);
        void Advise(IntPtr events, out uint cookie); void Unadvise(uint cookie);
        void SetOptions(uint options); void GetOptions(out uint options);
        void SetDefaultFolder(IShellItem item); void SetFolder(IShellItem item);
        void GetFolder(out IShellItem item); void GetCurrentSelection(out IShellItem item);
        void SetFileName([MarshalAs(UnmanagedType.LPWStr)] string name); void GetFileName(out IntPtr name);
        void SetTitle([MarshalAs(UnmanagedType.LPWStr)] string title);
        void SetOkButtonLabel([MarshalAs(UnmanagedType.LPWStr)] string label);
        void SetFileNameLabel([MarshalAs(UnmanagedType.LPWStr)] string label);
        void GetResult(out IShellItem item); void AddPlace(IShellItem item, uint alignment);
        void SetDefaultExtension([MarshalAs(UnmanagedType.LPWStr)] string extension);
        void Close(int result); void SetClientGuid(ref Guid guid); void ClearClientData(); void SetFilter(IntPtr filter);
    }
    [ComImport, Guid("43826D1E-E718-42EE-BC55-A1E261C37BFE"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IShellItem {
        void BindToHandler(IntPtr context, ref Guid handler, ref Guid iid, out IntPtr result);
        void GetParent(out IShellItem parent); void GetDisplayName(uint kind, out IntPtr name);
        void GetAttributes(uint mask, out uint attributes); void Compare(IShellItem other, uint hint, out int order);
    }
    [DllImport("shell32.dll", CharSet=CharSet.Unicode, PreserveSig=true)]
    static extern int SHCreateItemFromParsingName(string path, IntPtr context, ref Guid iid, out IShellItem item);

    public static string Choose(IntPtr owner, string initial) {
        object instance = Activator.CreateInstance(Type.GetTypeFromCLSID(new Guid("DC1C5A9C-E88A-4DDE-A5A1-60F82A20AEF7")));
        var dialog = (IFileOpenDialog)instance;
        try {
            // Folder-only, filesystem-only, keep working directory and shell recent history unchanged.
            dialog.SetOptions(0x20 | 0x40 | 0x800 | 0x8 | 0x02000000);
            dialog.SetTitle("Save mobile libraries to"); dialog.SetOkButtonLabel("Use this folder");
            if (!String.IsNullOrEmpty(initial)) {
                IShellItem folder; Guid iid = new Guid("43826D1E-E718-42EE-BC55-A1E261C37BFE");
                if (SHCreateItemFromParsingName(initial, IntPtr.Zero, ref iid, out folder) == 0) {
                    try { dialog.SetFolder(folder); } finally { Marshal.ReleaseComObject(folder); }
                }
            }
            int result = dialog.Show(owner);
            if (unchecked((uint)result) == 0x800704C7) return null;
            Marshal.ThrowExceptionForHR(result);
            IShellItem selected; dialog.GetResult(out selected);
            try {
                IntPtr text; selected.GetDisplayName(0x80058000, out text);
                try { return Marshal.PtrToStringUni(text); } finally { Marshal.FreeCoTaskMem(text); }
            } finally { Marshal.ReleaseComObject(selected); }
        } finally { Marshal.ReleaseComObject(instance); }
    }
}
'@
$owner = New-Object System.Windows.Forms.Form
$owner.Text = 'Mobile library folder picker'
$owner.Width = 460; $owner.Height = 150
$owner.StartPosition = 'CenterScreen'; $owner.TopMost = $true
$label = New-Object System.Windows.Forms.Label
$label.Dock = 'Fill'; $label.Padding = New-Object System.Windows.Forms.Padding(16)
$label.Text = 'Opening the Windows folder browser. If it stalls, use Close picker in the toolkit and paste your save folder instead.'
$owner.Controls.Add($label)
try {
    $owner.Show(); $owner.Activate(); [System.Windows.Forms.Application]::DoEvents()
    @{state='ready'} | ConvertTo-Json -Compress | Set-Content -LiteralPath ($ResultPath + '.ready') -Encoding UTF8
    $selected = [MobileLibraryFolderPicker]::Choose($owner.Handle, $InitialPath)
    @{folder=$selected} | ConvertTo-Json -Compress | Set-Content -LiteralPath $ResultPath -Encoding UTF8
} catch {
    @{error='The Windows folder browser could not open. Paste the destination folder instead.'} | ConvertTo-Json -Compress | Set-Content -LiteralPath $ResultPath -Encoding UTF8
    exit 1
} finally { $owner.Close(); $owner.Dispose() }
