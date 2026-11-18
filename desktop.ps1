# chiiOS 바탕화면: 지금 Windows 바탕화면의 아이콘과 자리를 그대로 읽어 둔다.
# 홈 화면의 [바탕화면] 이 이걸 보고 같은 배치로 그리고, 두 번 누르면 그 항목을 Windows 에서 연다.
# 자리는 탐색기에게 직접 묻는다(바탕화면 보기의 IFolderView). 레지스트리에 남은 옛 배치가 아니라 지금 보이는 그대로다.
# 그림은 탐색기가 실제로 그리는 것(IShellItemImageFactory)이라 스팀 게임 바로가기 아이콘도 같다.
#
#   powershell -ExecutionPolicy Bypass -File desktop.ps1      레포의 .cache\desktop 에 layout.json 과 아이콘을 쓴다
param([string]$Out = (Join-Path $PSScriptRoot '.cache\desktop'), [int]$Size = 64)
$ErrorActionPreference = 'Stop'

Add-Type -ReferencedAssemblies System.Drawing -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;

namespace ChiiDesk {
  [StructLayout(LayoutKind.Sequential)] public struct POINT { public int X, Y; }
  [StructLayout(LayoutKind.Sequential)] public struct SIZE { public int cx, cy; }
  [StructLayout(LayoutKind.Sequential)] struct BITMAP { public int bmType, bmWidth, bmHeight, bmWidthBytes; public ushort bmPlanes, bmBitsPixel; public IntPtr bmBits; }

  [ComImport, Guid("6D5140C1-7436-11CE-8034-00AA006009FA"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IServiceProvider {
    [PreserveSig] int QueryService(ref Guid guidService, ref Guid riid, [MarshalAs(UnmanagedType.IUnknown)] out object ppv);
  }

  [ComImport, Guid("000214E2-0000-0000-C000-000000000046"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IShellBrowser {
    void GetWindow(out IntPtr phwnd);
    void ContextSensitiveHelp(int f);
    void InsertMenusSB(IntPtr a, IntPtr b);
    void SetMenuSB(IntPtr a, IntPtr b, IntPtr c);
    void RemoveMenusSB(IntPtr a);
    void SetStatusTextSB(IntPtr a);
    void EnableModelessSB(int f);
    void TranslateAcceleratorSB(IntPtr a, ushort b);
    void BrowseObject(IntPtr a, uint b);
    void GetViewStateStream(uint a, out IntPtr b);
    void GetControlWindow(uint a, out IntPtr b);
    void SendControlMsg(uint a, uint b, IntPtr c, IntPtr d, out IntPtr e);
    void QueryActiveShellView([MarshalAs(UnmanagedType.IUnknown)] out object ppshv);
  }

  [ComImport, Guid("cde725b0-ccc9-4519-917e-325d72fab4ce"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IFolderView {
    void GetCurrentViewMode(out uint mode);
    void SetCurrentViewMode(uint mode);
    void GetFolder(ref Guid riid, [MarshalAs(UnmanagedType.IUnknown)] out object ppv);
    void Item(int i, out IntPtr ppidl);
    void ItemCount(uint flags, out int count);
    void Items(uint flags, ref Guid riid, [MarshalAs(UnmanagedType.IUnknown)] out object ppv);
    void GetSelectionMarkedItem(out int i);
    void GetFocusedItem(out int i);
    void GetItemPosition(IntPtr pidl, out POINT pt);
    void GetSpacing(ref POINT pt);
  }

  [ComImport, Guid("bcc18b79-ba16-442f-80c4-8a59c30c463b"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IShellItemImageFactory {
    [PreserveSig] int GetImage(SIZE size, int flags, out IntPtr phbm);
  }

  public class Item {
    public string Name;
    public string Parse;
    public int X, Y;
    public Bitmap Icon;
  }

  public static class Desk {
    [DllImport("shell32.dll", CharSet = CharSet.Unicode)]
    static extern int SHGetNameFromIDList(IntPtr pidl, uint sigdn, out IntPtr name);
    [DllImport("shell32.dll")]
    static extern int SHCreateItemFromIDList(IntPtr pidl, ref Guid riid, [MarshalAs(UnmanagedType.IUnknown)] out object ppv);
    [DllImport("gdi32.dll")] static extern int GetObject(IntPtr h, int c, ref BITMAP bm);
    [DllImport("gdi32.dll")] static extern bool DeleteObject(IntPtr h);
    [DllImport("ole32.dll")] static extern void CoTaskMemFree(IntPtr p);
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();

    static string Name(IntPtr pidl, uint sigdn) {
      IntPtr p;
      if (SHGetNameFromIDList(pidl, sigdn, out p) != 0) return null;
      string s = Marshal.PtrToStringUni(p);
      CoTaskMemFree(p);
      return s;
    }

    // 탐색기가 만든 아이콘 비트맵(알파 있는 DIB)을 알파 그대로 옮긴다. FromHbitmap 은 알파를 버려 바탕이 검게 나온다.
    static Bitmap ToBitmap(IntPtr hbm) {
      BITMAP bm = new BITMAP();
      GetObject(hbm, Marshal.SizeOf(typeof(BITMAP)), ref bm);
      if (bm.bmBits == IntPtr.Zero || bm.bmBitsPixel != 32) {
        return Image.FromHbitmap(hbm);
      }
      Bitmap view = new Bitmap(bm.bmWidth, bm.bmHeight, bm.bmWidthBytes, PixelFormat.Format32bppPArgb, bm.bmBits);
      Bitmap copy = new Bitmap(bm.bmWidth, bm.bmHeight, PixelFormat.Format32bppArgb);
      using (Graphics g = Graphics.FromImage(copy)) { g.DrawImage(view, 0, 0, bm.bmWidth, bm.bmHeight); }
      view.Dispose();
      // DIB 는 아래쪽 줄부터 담긴다.
      copy.RotateFlip(RotateFlipType.RotateNoneFlipY);
      return copy;
    }

    public static POINT Spacing;

    public static List<Item> Read(int size) {
      Type t = Type.GetTypeFromCLSID(new Guid("9BA05972-F6A8-11CF-A442-00A0C90A8F39"));
      object windows = Activator.CreateInstance(t);
      object loc = 0;            // CSIDL_DESKTOP
      object empty = null;
      object[] args = new object[] { loc, empty, 8, 0, 1 };   // SWC_DESKTOP, SWFO_NEEDDISPATCH
      System.Reflection.ParameterModifier mod = new System.Reflection.ParameterModifier(5);
      mod[3] = true;
      object disp = t.InvokeMember("FindWindowSW", System.Reflection.BindingFlags.InvokeMethod, null, windows, args,
        new System.Reflection.ParameterModifier[] { mod }, null, null);
      Guid sidTop = new Guid("4C96BE40-915C-11CF-99D3-00AA004AE837");   // SID_STopLevelBrowser
      Guid iidBrowser = typeof(IShellBrowser).GUID;
      object browserObj;
      int hr = ((IServiceProvider)disp).QueryService(ref sidTop, ref iidBrowser, out browserObj);
      if (hr != 0) throw new Exception("바탕화면 보기를 못 찾았다 (" + hr + ")");
      object viewObj;
      ((IShellBrowser)browserObj).QueryActiveShellView(out viewObj);
      IFolderView view = (IFolderView)viewObj;
      POINT sp = new POINT();
      view.GetSpacing(ref sp);
      Spacing = sp;
      int count;
      view.ItemCount(2, out count);   // SVGIO_ALLVIEW
      Guid iidImg = typeof(IShellItemImageFactory).GUID;
      List<Item> items = new List<Item>();
      for (int i = 0; i < count; i++) {
        IntPtr pidl;
        view.Item(i, out pidl);
        try {
          Item it = new Item();
          POINT pt;
          view.GetItemPosition(pidl, out pt);
          it.X = pt.X; it.Y = pt.Y;
          it.Name = Name(pidl, 0);                    // SIGDN_NORMALDISPLAY
          it.Parse = Name(pidl, 0x80028000);          // SIGDN_DESKTOPABSOLUTEPARSING
          object f;
          if (SHCreateItemFromIDList(pidl, ref iidImg, out f) == 0) {
            IntPtr hbm;
            SIZE s = new SIZE(); s.cx = size; s.cy = size;
            if (((IShellItemImageFactory)f).GetImage(s, 0, out hbm) == 0) {
              it.Icon = ToBitmap(hbm);
              DeleteObject(hbm);
            }
          }
          items.Add(it);
        } finally {
          CoTaskMemFree(pidl);
        }
      }
      return items;
    }
  }
}
'@

# 탐색기는 화면 배율을 아는 프로그램이라 자리를 실제 픽셀로 준다. 이쪽도 맞춰야 화면 크기와 비교할 수 있다.
[ChiiDesk.Desk]::SetProcessDPIAware() | Out-Null
Add-Type -AssemblyName System.Windows.Forms
$items = [ChiiDesk.Desk]::Read($Size)

$iconDir = Join-Path $Out 'icons'
New-Item -ItemType Directory -Force -Path $iconDir | Out-Null
Get-ChildItem $iconDir -Filter *.png -ErrorAction SilentlyContinue | Remove-Item -Force
$sha = [System.Security.Cryptography.SHA1]::Create()
$list = @()
foreach ($it in $items) {
    $key = if ($it.Parse) { $it.Parse } else { $it.Name }
    $id = -join ($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($key))[0..7] | ForEach-Object { $_.ToString('x2') })
    if ($it.Icon) {
        $it.Icon.Save((Join-Path $iconDir "$id.png"), [System.Drawing.Imaging.ImageFormat]::Png)
        $it.Icon.Dispose()
    }
    $list += [pscustomobject]@{ id = $id; name = $it.Name; parse = $it.Parse; x = $it.X; y = $it.Y; icon = [bool]$it.Icon }
}
$screen = [System.Windows.Forms.SystemInformation]::VirtualScreen
$layout = [pscustomobject]@{
    t = [int][double]::Parse((Get-Date -UFormat %s))
    spacing = [pscustomobject]@{ x = [ChiiDesk.Desk]::Spacing.X; y = [ChiiDesk.Desk]::Spacing.Y }
    screen = [pscustomobject]@{ x = $screen.X; y = $screen.Y; w = $screen.Width; h = $screen.Height }
    items = $list
}
# BOM 없는 UTF-8 로 쓴다. Debian 쪽 python 이 그대로 읽는다.
$json = $layout | ConvertTo-Json -Depth 4
[IO.File]::WriteAllText((Join-Path $Out 'layout.json'), $json, (New-Object System.Text.UTF8Encoding $false))
"바탕화면 항목 $($list.Count)개 -> $Out"
