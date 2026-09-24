using Avalonia;
using Avalonia.Controls;
using Avalonia.Layout;
using Avalonia.Media;
using Xp.Launcher.Core;

namespace Xp.Launcher;

/// <summary>
/// The account block in Settings. The launcher never takes a password: it asks the site for a short
/// code, the person confirms it there while already signed in, and the launcher gets a key of its
/// own. The key can be given back from here, and taken away from the site at any time.
/// </summary>
public sealed class AccountPanel : StackPanel
{
    static readonly HttpClient Http = new() { Timeout = TimeSpan.FromSeconds(30) };

    readonly Settings _settings;
    readonly DeviceStore _store;

    readonly TextBlock _who = new() { FontSize = 13, TextWrapping = TextWrapping.Wrap };
    readonly TextBlock _hint = new() { FontSize = 12, Foreground = Skin.B(Skin.Muted), TextWrapping = TextWrapping.Wrap };
    readonly TextBlock _code = new() { FontSize = 30, FontFamily = Skin.Medium, IsVisible = false, HorizontalAlignment = HorizontalAlignment.Center, Margin = new Thickness(0, 4) };
    readonly Button _link, _open, _cancel, _unlink;

    DeviceAccount? _account;
    CancellationTokenSource? _waiting;

    public AccountPanel(Settings settings)
    {
        _settings = settings;
        _store = new DeviceStore(Path.Combine(Settings.Dir, "device.json"));
        Spacing = 10;

        _link = Skin.Btn(L.T("account.link"));
        _link.HorizontalAlignment = HorizontalAlignment.Stretch;
        _link.Click += async (_, _) => await StartAsync();
        _open = Skin.Btn(L.T("account.open"), "primary");
        _open.HorizontalAlignment = HorizontalAlignment.Stretch;
        _open.IsVisible = false;
        _open.Click += (_, _) => ReportWindow.OpenUrl(SiteUrl());
        _cancel = Skin.Btn(L.T("account.cancel"), "ghost");
        _cancel.HorizontalAlignment = HorizontalAlignment.Stretch;
        _cancel.IsVisible = false;
        _cancel.Click += (_, _) => { _waiting?.Cancel(); Show(); };
        _unlink = Skin.Btn(L.T("account.unlink"), "warn");
        _unlink.HorizontalAlignment = HorizontalAlignment.Stretch;
        _unlink.IsVisible = false;
        _unlink.Click += async (_, _) => await UnlinkAsync();

        Children.Add(Skin.H2(L.T("account.title")));
        Children.Add(_who);
        Children.Add(_code);
        Children.Add(_hint);
        Children.Add(_link);
        Children.Add(_open);
        Children.Add(_cancel);
        Children.Add(_unlink);

        _account = _store.Load();
        Show();
    }

    /// <summary>
    /// Asks the site whether the stored key still works. A link taken away there must not go on
    /// looking alive here, and an unreachable site is no reason to forget anything.
    /// </summary>
    public async Task CheckAsync()
    {
        if (_account is not { } a || Portal() is not { } portal) return;
        try
        {
            if (await new PortalClient(Http, portal).WhoAmIAsync(a.Token, CancellationToken.None) is { } view)
            {
                if (view.Account != a.Account) { a.Account = view.Account; _store.Save(a); Show(); }
                return;
            }
            _store.Clear();
            _account = null;
            Show(L.T("account.revoked"));
        }
        catch (Exception e) when (e is HttpRequestException or TaskCanceledException or PortalException) { }
    }

    /// <summary>The name the site will show in the list of linked launchers: ours, never the machine's.</summary>
    static string DeviceName() => L.T("account.deviceName", BuiltIn.VersionText);

    Uri? Portal()
    {
        var url = _settings.PortalUrl ?? BuiltIn.Defaults.PortalUrl;
        return Uri.TryCreate(url, UriKind.Absolute, out var uri) ? uri : null;
    }

    string _pendingCode = "";
    Guid _pendingDevice;

    string SiteUrl()
    {
        var b = Portal()!.AbsoluteUri.TrimEnd('/');
        return _pendingCode.Length > 0 ? $"{b}/me/devices?code={Uri.EscapeDataString(_pendingCode)}" : $"{b}/me/devices";
    }

    void Show(string? error = null)
    {
        bool waiting = _pendingCode.Length > 0;
        _code.IsVisible = waiting;
        _code.Text = _pendingCode;
        _open.IsVisible = waiting;
        _cancel.IsVisible = waiting;
        _link.IsVisible = !waiting && _account is null;
        _unlink.IsVisible = !waiting && _account is not null;
        _who.Text = error is not null ? error
            : waiting ? L.T("account.waiting")
            : _account is { } a ? L.T("account.linkedAs", a.Account)
            : L.T("account.none");
        _who.Foreground = Skin.B(error is not null ? Skin.WarnText : _account is not null ? Skin.Text : Skin.Text2);
        _hint.Text = waiting ? L.T("account.codeHint") : _account is null ? L.T("account.hint") : L.T("account.unlinkHint");
    }

    /// <summary>Asks the site for a code and then waits for the person to say yes over there.</summary>
    async Task StartAsync()
    {
        if (Portal() is not { } portal) { Show(L.T("account.noPortal")); return; }
        _link.IsEnabled = false;
        try
        {
            var client = new PortalClient(Http, portal);
            var start = await client.StartLinkAsync(DeviceName(), CancellationToken.None);
            _pendingCode = start.Code;
            _pendingDevice = start.DeviceId;
            Show();
            ReportWindow.OpenUrl(SiteUrl());
            await WaitAsync(client, TimeSpan.FromSeconds(Math.Clamp(start.ExpiresIn, 60, 3600)));
        }
        catch (Exception e) when (e is HttpRequestException or TaskCanceledException or PortalException)
        {
            _pendingCode = "";
            Show(Reason(e));
        }
        finally { _link.IsEnabled = true; }
    }

    async Task WaitAsync(PortalClient client, TimeSpan life)
    {
        _waiting?.Cancel();
        using var cts = new CancellationTokenSource(life);
        _waiting = cts;
        var device = _pendingDevice;
        try
        {
            while (!cts.IsCancellationRequested)
            {
                // the person is walking to the browser: asking twice a second would be rude to the site and to them
                await Task.Delay(TimeSpan.FromSeconds(2), cts.Token);
                var status = await client.LinkStatusAsync(device, cts.Token);
                if (status.Status == "expired") break;
                if (status.Token is not { Length: > 0 } token) continue;
                var account = new DeviceAccount
                {
                    Token = token,
                    Account = status.Account ?? "",
                    Name = DeviceName(),
                    LinkedAt = DateTimeOffset.UtcNow,
                };
                _store.Save(account);
                _account = account;
                _pendingCode = "";
                Show();
                return;
            }
            _pendingCode = "";
            Show(L.T("account.expired"));
        }
        catch (OperationCanceledException)
        {
            // the person pressed cancel, or the code outlived its ten minutes
            _pendingCode = "";
            Show(L.T("account.expired"));
        }
        catch (Exception e) when (e is HttpRequestException or PortalException)
        {
            _pendingCode = "";
            Show(Reason(e));
        }
        finally { if (ReferenceEquals(_waiting, cts)) _waiting = null; }
    }

    async Task UnlinkAsync()
    {
        if (_account is not { } a) return;
        _unlink.IsEnabled = false;
        try
        {
            // the key is given back first, but it leaves this machine either way: a launcher that
            // cannot reach the site must still be able to stop working for this account
            if (Portal() is { } portal)
                try { await new PortalClient(Http, portal).ForgetAsync(a.Token, CancellationToken.None); }
                catch (Exception e) when (e is HttpRequestException or TaskCanceledException or PortalException) { }
            _store.Clear();
            _account = null;
            Show();
        }
        finally { _unlink.IsEnabled = true; }
    }

    static string Reason(Exception e) => e switch
    {
        PortalException p => L.T("account.error", p.Code),
        _ => L.T("account.offline"),
    };
}
