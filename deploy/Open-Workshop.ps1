param([string]$PiAddress)
$ErrorActionPreference = 'Stop'
$keyPath = Join-Path $env:USERPROFILE '.ssh\id_rsa'
if (!(Test-Path -LiteralPath $keyPath)) { throw "SSH key missing: $keyPath" }
$addresses = if ($PiAddress) { @($PiAddress) } else { @('10.77.0.1', '192.168.1.61') }
$selected = $null
foreach ($address in $addresses) {
    & ssh -i $keyPath -o BatchMode=yes -o HostKeyAlias=192.168.1.61 -o ConnectTimeout=4 "user@$address" 'true'
    if ($LASTEXITCODE -eq 0) { $selected = $address; break }
}
if (!$selected) { throw 'Could not reach the Pi. Connect the Ethernet cable or use the same Wi-Fi network. On a new laptop, install your authorized SSH key and accept the Pi host key with a normal SSH connection first.' }
$listener = Get-NetTCPConnection -LocalPort 17745 -State Listen -ErrorAction SilentlyContinue
if ($listener) { throw 'Port 17745 is already in use. Close the previous Workshop connection window and try again.' }
$sshArgs = @('-i', ('"' + $keyPath + '"'), '-o', 'BatchMode=yes', '-o', 'HostKeyAlias=192.168.1.61', '-o', 'ExitOnForwardFailure=yes', '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=3', '-N', '-L', '127.0.0.1:17745:127.0.0.1:17745', "user@$selected")
$tunnel = Start-Process -FilePath 'ssh.exe' -ArgumentList $sshArgs -WindowStyle Hidden -PassThru
try {
    $ready = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        if ($tunnel.HasExited) { throw 'SSH tunnel failed to start.' }
        try {
            $response = Invoke-WebRequest 'http://127.0.0.1:17745/workshop/' -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -eq 200) { $ready = $true; break }
        } catch { Start-Sleep -Milliseconds 200 }
    }
    if (!$ready) { throw 'The companion app did not respond.' }
    Start-Process 'http://127.0.0.1:17745/workshop/'
    Write-Host "Workshop connected to $selected. Keep this window open while editing."
    Read-Host 'Press Enter to disconnect when finished'
} finally {
    if (!$tunnel.HasExited) { Stop-Process -Id $tunnel.Id }
}
