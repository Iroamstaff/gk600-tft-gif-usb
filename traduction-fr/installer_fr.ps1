# Ajoute la langue francaise (LCID 1036) au logiciel du clavier
# MSI FORGE GK600 / Erazer MK85Pro Driver
# A lancer via INSTALLER_FR.bat (il demande les droits administrateur)
#
# Dossiers traites :
#  - si ce script est a cote de DeviceDriver.exe : ce dossier seulement ;
#  - sinon : les dossiers d'installation dans Program Files, plus les copies
#    du logiciel posees sur le Bureau (dossier avec DeviceDriver.exe et config.xml).

$ErrorActionPreference = 'Stop'
$src = Join-Path $PSScriptRoot '1036.lan'

Write-Host ''
Write-Host '=== Ajout du francais au logiciel du clavier GK600 ===' -ForegroundColor Cyan
Write-Host ''

if (-not (Test-Path -LiteralPath $src)) {
    Write-Host "ERREUR : 1036.lan est introuvable a cote du script." -ForegroundColor Red
    exit 1
}

if (Get-Process -Name 'DeviceDriver' -ErrorAction SilentlyContinue) {
    Write-Host "Le logiciel du clavier est ouvert." -ForegroundColor Yellow
    Write-Host "Fermez-le (zone de notification incluse) puis relancez ce script." -ForegroundColor Yellow
    exit 1
}

$targets = @()
if (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'DeviceDriver.exe')) {
    $targets += $PSScriptRoot
}
else {
    $targets += 'C:\Program Files (x86)\MSI FORGE GK600'
    $targets += 'C:\Program Files (x86)\Womier SK80 PRO Driver'
    $desk = [Environment]::GetFolderPath('Desktop')
    if ($desk -and (Test-Path -LiteralPath $desk)) {
        $targets += @(Get-ChildItem -LiteralPath $desk -Filter 'DeviceDriver.exe' -Recurse -Depth 2 -ErrorAction SilentlyContinue |
            Where-Object { Test-Path -LiteralPath (Join-Path $_.DirectoryName 'config.xml') } |
            ForEach-Object { $_.DirectoryName })
    }
}
$targets = @($targets | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -Unique)

if ($targets.Count -eq 0) {
    Write-Host "ERREUR : aucun dossier du logiciel trouve." -ForegroundColor Red
    Write-Host "Mettez 1036.lan, installer_fr.ps1 et INSTALLER_FR.bat a cote de DeviceDriver.exe," -ForegroundColor Yellow
    Write-Host "puis relancez INSTALLER_FR.bat depuis ce dossier." -ForegroundColor Yellow
    exit 1
}

$needAdmin = @($targets | Where-Object { $_ -like '*\Program Files*' }).Count -gt 0
if ($needAdmin) {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $isAdmin = (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $isAdmin) {
        Write-Host "ERREUR : relancez ce script en tant qu'administrateur." -ForegroundColor Red
        exit 1
    }
}

$newBlock = @"
<language.info default_lan="1036">
		<lan value="1036" />
		<lan value="1033" />
		<lan value="2052" />
		<lan value="1028" />
	</language.info>
"@

# Le logiciel lit le .lan en UTF-16 LE avec BOM et fins de ligne CRLF :
# on le reecrit dans ce format, quel que soit l'encodage du fichier fourni.
$lan = [System.IO.File]::ReadAllText($src)
$lan = $lan -replace "`r?`n", "`r`n"
$utf16Bom = New-Object System.Text.UnicodeEncoding($false, $true)

foreach ($dir in $targets) {
    Write-Host ("--- " + $dir) -ForegroundColor White

    $langDir = Join-Path $dir 'language'
    if (-not (Test-Path -LiteralPath $langDir)) {
        New-Item -ItemType Directory -Force -Path $langDir | Out-Null
    }
    [System.IO.File]::WriteAllText((Join-Path $langDir '1036.lan'), $lan, $utf16Bom)
    Write-Host '    [ok] language\1036.lan copie' -ForegroundColor Green

    $cfg = Join-Path $dir 'config.xml'
    if (Test-Path -LiteralPath $cfg) {
        $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
        $bak = "$cfg.bak-$stamp"
        Copy-Item -LiteralPath $cfg -Destination $bak -Force
        Write-Host ('    [ok] sauvegarde : config.xml.bak-' + $stamp) -ForegroundColor Green

        $txt = [System.IO.File]::ReadAllText($cfg, [System.Text.Encoding]::UTF8)
        if ($txt -match '(?s)<language\.info.*?</language\.info>') {
            $txt = $txt -replace '(?s)<language\.info.*?</language\.info>', $newBlock
            $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
            [System.IO.File]::WriteAllText($cfg, $txt, $utf8NoBom)
            Write-Host '    [ok] config.xml : francais ajoute et defini par defaut' -ForegroundColor Green
        }
        else {
            Write-Host '    [!!] bloc language.info introuvable : config.xml inchange' -ForegroundColor Yellow
        }
    }
    else {
        Write-Host '    [!!] config.xml introuvable dans ce dossier' -ForegroundColor Yellow
    }
}

# Langue selectionnee : stockee dans HKCU par le logiciel
$regKeys = @(
    'HKCU:\Software\Erazer MK85Pro Driver',
    'HKCU:\Software\MSI FORGE GK600 Driver',
    'HKCU:\Software\Womier SK80 PRO Driver'
)
$regDone = 0
foreach ($k in $regKeys) {
    if (Test-Path -LiteralPath $k) {
        Set-ItemProperty -LiteralPath $k -Name 'LCID' -Value '1036' -Type String
        Write-Host ('    [ok] LCID=1036 -> ' + $k) -ForegroundColor Green
        $regDone++
    }
}

Write-Host ''
if ($regDone -gt 0) {
    Write-Host 'Termine. Lancez le logiciel : il doit etre en francais.' -ForegroundColor Cyan
}
else {
    Write-Host 'Termine (cle de registre non trouvee sous ce compte).' -ForegroundColor Cyan
    Write-Host 'Lancez le logiciel, puis Parametres > Language > Francais.' -ForegroundColor Cyan
}
Write-Host ''
Write-Host 'Pour revenir en anglais : Parametres > Langue > English,' -ForegroundColor DarkGray
Write-Host "ou restaurez le fichier config.xml.bak-* cree a cote de config.xml." -ForegroundColor DarkGray
Write-Host ''
