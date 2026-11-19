# Runner TLS/证书排查（只读）
$ErrorActionPreference = "Continue"
Write-Host "=== 时间/时区 ==="
Get-Date -Format o
(Get-TimeZone).Id

Write-Host "`n=== 代理环境变量 ==="
Get-ChildItem Env: | Where-Object { $_.Name -match 'proxy' } |
  ForEach-Object { "{0}={1}" -f $_.Name, $_.Value }

Write-Host "`n=== WinHTTP 代理 ==="
netsh winhttp show proxy 2>&1

$targets = @("github.com", "api.github.com", "broker.actions.githubusercontent.com")
foreach ($target in $targets) {
  Write-Host ("`n=== " + $target + ":443 ===")
  try {
    $tcp = New-Object System.Net.Sockets.TcpClient
    $tcp.Connect($target, 443)
    $ssl = New-Object System.Net.Security.SslStream($tcp.GetStream(), $false, {
      param($sender, $cert, $chain, $errors)
      Write-Host ("  TLS errors: {0}" -f $errors)
      if ($cert) {
        Write-Host ("  Subject: {0}" -f $cert.Subject)
        Write-Host ("  Issuer : {0}" -f $cert.Issuer)
        Write-Host ("  NotAfter: {0}" -f $cert.GetExpirationDateString())
        Write-Host ("  Thumbprint: {0}" -f $cert.GetCertHashString())
      }
      return $true
    })
    $ssl.AuthenticateAsClient($target)
    Write-Host ("  TLS: {0}" -f $ssl.SslProtocol)
    $ssl.Dispose(); $tcp.Close()
  } catch {
    Write-Host ("  FAILED: {0}" -f $_.Exception.Message)
    if ($_.Exception.InnerException) { Write-Host ("  inner: {0}" -f $_.Exception.InnerException.Message) }
  }
}

Write-Host "`n=== 证书链（github.com）==="
try {
  $req = [Net.HttpWebRequest]::Create("https://github.com")
  $req.Timeout = 15000
  $resp = $req.GetResponse()
  $resp.Close()
  Write-Host "  HTTPS OK"
} catch {
  Write-Host ("  HTTPS FAILED: {0}" -f $_.Exception.Message)
}
Write-Host "`nDONE"
