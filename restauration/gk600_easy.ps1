<#
  gk600_easy.ps1 - EXPERIMENTAL - beginner launcher for gk600_restore.py, gk600_home_picture.py
  and gk600_boot_animation.py
  Started by GK600-Repair.bat (repair the screen menus and the boot animation), by
  GK600-Home-Picture.bat (replace the home-screen dragon with your own picture) or by
  GK600-Boot-Animation.bat (replace the MSI boot animation with your own GIF), or by
  ..\panneau\GK600-Panel.bat (the panel: GIF, RGB effects and all of the above in one window).

  First run: downloads a portable Python 3.13 (python.org), the hidapi module (PyPI), Pillow for
  pictures (PyPI) and the public GK600 dump (github.com/Flonfli). Every file is checked against
  its SHA-256. Nothing is installed on Windows: everything stays in the .\runtime folder.
#>
param(
    [ValidateSet('repair', 'picture', 'boot', 'panel')] [string]$Mode = 'repair',
    [string]$Picture = '',
    [ValidateSet('auto', 'fr', 'en')] [string]$Lang = 'auto',
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch { }

try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }

$Here = $PSScriptRoot
Set-Location -LiteralPath $Here
# PowerShell names are case-insensitive: this flag must not be called $fr (parameter of T below)
if ($Lang -eq 'auto') {
    $script:IsFrench = ((Get-UICulture).TwoLetterISOLanguageName -eq 'fr') -or ((Get-Culture).TwoLetterISOLanguageName -eq 'fr')
} else {
    $script:IsFrench = ($Lang -eq 'fr')
}

function T([string]$fr, [string]$en) { if ($script:IsFrench) { $fr } else { $en } }
function Say([string]$fr, [string]$en, [string]$color = 'Gray') { Write-Host (T $fr $en) -ForegroundColor $color }
function Step([string]$fr, [string]$en) { Write-Host ''; Write-Host ('=== ' + (T $fr $en)) -ForegroundColor Cyan }
function Wait-Enter([string]$fr, [string]$en) { [void](Read-Host (T $fr $en)) }
function Ask-YesNo([string]$fr, [string]$en) {
    while ($true) {
        $a = ([string](Read-Host ((T $fr $en) + (T ' (O/N)' ' (Y/N)')))).Trim().ToUpper()
        if ($a -in @('O', 'OUI', 'Y', 'YES')) { return $true }
        if ($a -in @('N', 'NON', 'NO')) { return $false }
    }
}
function Fail([string]$fr, [string]$en) {
    Write-Host ''
    Write-Host (T $fr $en) -ForegroundColor Red
    Say "Le journal gk600_restore.log se trouve dans ce dossier : joins-le si tu demandes de l'aide." `
        "The log file gk600_restore.log is in this folder: attach it if you ask for help." 'Yellow'
    exit 1
}

# ------------------------------------------------------------------ files, all pinned by SHA-256
$Runtime = Join-Path $Here 'runtime'
$PyDir = Join-Path $Runtime 'python'
$Py = Join-Path $PyDir 'python.exe'
$DumpPath = Join-Path $Here 'Forge gk600 tkl wireless.bin'

$PYTHON = @{ Name = 'python-3.13.17-embed-amd64.zip'
             Sha  = '9e35319bffedab8b36ad44d8f377cb4f1733bcec257a0b6d04d94f01486ddb38'
             Url  = 'https://www.python.org/ftp/python/3.13.17/python-3.13.17-embed-amd64.zip' }
$HIDAPI = @{ Name = 'hidapi-0.15.0-cp313-cp313-win_amd64.whl'
             Sha  = '04e0c1ed6d742bc6e1d00599394bec6b2afb8ee2fc5a0a183d3c4c2d4e315c34'
             Url  = 'https://files.pythonhosted.org/packages/d9/00/7dd3f866a748b0c9eb4adedaa025ec8c533ed1946e9e918661c948a5c0f4/hidapi-0.15.0-cp313-cp313-win_amd64.whl' }
$PILLOW = @{ Name = 'pillow-13.0.0-cp313-cp313-win_amd64.whl'
             Sha  = '9dda0788a9932776a75d8bcc020076edc308ce2508b51f6739a45e3158b3fc42'
             Url  = 'https://files.pythonhosted.org/packages/d7/ed/1b16fb66a37e1b9e41370b93b2c614c7da761a5b2a41dc333f7af4639962/pillow-13.0.0-cp313-cp313-win_amd64.whl' }
# firmware versions on which the repair has been confirmed on a real keyboard
$Validated = @('V1.04', 'V1.20')

$DUMP   = @{ Name = 'Forge gk600 tkl wireless.bin'
             Sha  = 'd3a7359a69692e2d25994b8c886cdd87444342b509eaf505cb197664ab671b50'
             Url  = 'https://raw.githubusercontent.com/Flonfli/Forge-gk600-tkl-wireless.bin/main/Forge%20gk600%20tkl%20wireless.bin' }

function Test-Sha([string]$path, [string]$sha) {
    (Test-Path -LiteralPath $path) -and ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLower() -eq $sha)
}

function Get-Checked($item, [string]$dest) {
    if (Test-Sha $dest $item.Sha) { return }
    Say ('  téléchargement : ' + $item.Name) ('  downloading: ' + $item.Name)
    $part = $dest + '.part'
    try {
        Invoke-WebRequest -UseBasicParsing -Uri $item.Url -OutFile $part
    } catch {
        Fail ("Téléchargement impossible (connexion Internet ?) : " + $item.Url + "`n" + $_.Exception.Message) `
             ("Download failed (Internet connection?): " + $item.Url + "`n" + $_.Exception.Message)
    }
    if (-not (Test-Sha $part $item.Sha)) {
        Remove-Item -LiteralPath $part -Force
        Fail ('Empreinte SHA-256 incorrecte pour ' + $item.Name + ' : fichier supprimé, rien n''a été utilisé.') `
             ('Wrong SHA-256 for ' + $item.Name + ': file deleted, nothing was used.')
    }
    Move-Item -LiteralPath $part -Destination $dest -Force
}

Add-Type -AssemblyName System.IO.Compression.FileSystem
function Expand-Entries([string]$zip, [string]$dest, [string]$pattern) {
    $z = [IO.Compression.ZipFile]::OpenRead($zip)
    try {
        foreach ($e in $z.Entries) {
            if ($e.Name -and ($e.FullName -like $pattern)) {
                $out = Join-Path $dest ($e.FullName -replace '/', '\')
                [void](New-Item -ItemType Directory -Force -Path (Split-Path -Parent $out))
                [IO.Compression.ZipFileExtensions]::ExtractToFile($e, $out, $true)
            }
        }
    } finally { $z.Dispose() }
}

function Prepare([bool]$needPillow) {
    Step "Préparation (la première fois : environ 35 Mo à télécharger, rien n'est installé sur Windows)" `
         "Setup (first time: about 35 MB to download, nothing is installed on Windows)"
    [void](New-Item -ItemType Directory -Force -Path $Runtime)
    if (-not (Test-Path -LiteralPath $Py)) {
        $z = Join-Path $Runtime $PYTHON.Name
        Get-Checked $PYTHON $z
        Expand-Entries $z $PyDir '*'
    }
    if (-not (Get-ChildItem -LiteralPath $PyDir -Filter 'hid*.pyd' -ErrorAction SilentlyContinue)) {
        $w = Join-Path $Runtime $HIDAPI.Name
        Get-Checked $HIDAPI $w
        Expand-Entries $w $PyDir 'hid*.pyd'
    }
    if ($needPillow -and -not (Test-Path -LiteralPath (Join-Path $PyDir 'PIL'))) {
        $w = Join-Path $Runtime $PILLOW.Name
        Get-Checked $PILLOW $w
        Expand-Entries $w $PyDir 'PIL/*'
    }
    Get-Checked $DUMP $DumpPath
    Say '  prêt' '  ready' 'Green'
}

# ------------------------------------------------------------------ keyboard steps
function Ensure-MsiClosed {
    while ($true) {
        $p = @(Get-Process -Name 'DeviceDriver', 'OpenRGB', 'SignalRgb' -ErrorAction SilentlyContinue)
        if ($p.Count -eq 0) { return }
        $names = ($p | Select-Object -ExpandProperty ProcessName -Unique) -join ', '
        Say ("Ferme d'abord : " + $names + " (pense à la zone de notification, près de l'horloge).") `
            ('Close this first: ' + $names + ' (check the system tray, next to the clock).') 'Yellow'
        Wait-Enter 'Puis appuie sur Entrée' 'Then press Enter'
    }
}

function Check-Keyboard([int]$tries = 1) {
    for ($i = 1; $i -le $tries; $i++) {
        $out = (& $Py 'gk600_restore.py' 'check' | Out-String)
        $code = $LASTEXITCODE
        if ($code -eq 0) {
            if ($out -match 'Firmware : (V[0-9]+\.[0-9]+)') { return $Matches[1] }
            return 'V?'
        }
        if ($i -lt $tries) { Start-Sleep -Seconds 3 }
    }
    Write-Host $out
    if ($out -match 'no GK600') {
        Fail "Clavier introuvable : branche le câble, mets l'interrupteur sur le mode filaire (USB), ferme le logiciel MSI, puis relance." `
             'Keyboard not found: plug the cable in, set the switch to wired (USB), close the MSI software, then try again.'
    }
    if ($out -match 'not idle') {
        Fail "Le clavier est occupé : éteins-le 10 secondes, rallume-le, puis relance." `
             'The keyboard is busy: switch it off for 10 seconds, switch it on, then try again.'
    }
    Fail 'Le clavier ne répond pas comme prévu (détails ci-dessus).' 'The keyboard did not answer as expected (details above).'
}

function Power-Cycle {
    Say 'Redémarre le clavier :' 'Restart the keyboard:' 'Yellow'
    Say '  1. débranche le câble USB' '  1. unplug the USB cable'
    Say "  2. éteins le clavier avec son interrupteur, attends 10 secondes" '  2. switch the keyboard off, wait 10 seconds'
    Say '  3. rallume-le et rebranche le câble (mode filaire)' '  3. switch it back on and plug the cable in (wired mode)'
    Wait-Enter "Appuie sur Entrée quand c'est fait" 'Press Enter when done'
    [void](Check-Keyboard 5)
}

function Run-Py([string[]]$arguments) {
    # Start-Process -NoNewWindow lets Python write straight to this console (live progress bar)
    $line = ($arguments | ForEach-Object { '"' + $_ + '"' }) -join ' '
    $p = Start-Process -FilePath $Py -ArgumentList $line -WorkingDirectory $Here -NoNewWindow -Wait -PassThru
    return $p.ExitCode
}

function Run-Write([string[]]$arguments) {
    if (-not $DryRun) { $arguments += '--write' }
    return (Run-Py $arguments)
}

function Banner([string]$fr, [string]$en) {
    Write-Host ''
    Write-Host '==========================================================' -ForegroundColor DarkCyan
    Write-Host ('  ' + (T $fr $en)) -ForegroundColor White
    Write-Host ('  ' + (T 'Expérimental, confirmé sur des GK600 TKL en firmware V1.04 et V1.20.' 'Experimental, confirmed on GK600 TKL keyboards running firmware V1.04 and V1.20.')) -ForegroundColor DarkGray
    if ($DryRun) { Write-Host '  DRY RUN: nothing will be written' -ForegroundColor Magenta }
    Write-Host '==========================================================' -ForegroundColor DarkCyan
}

if (-not (Test-Path -LiteralPath (Join-Path $Here 'gk600_restore.py'))) {
    Fail "gk600_restore.py est introuvable. Extrais d'abord tout le ZIP (clic droit > Extraire tout), puis relance depuis le dossier restauration." `
         'gk600_restore.py not found. Extract the whole ZIP first (right-click > Extract All), then run this again from the restauration folder.'
}

# ------------------------------------------------------------------ panel
if ($Mode -eq 'panel') {
    Banner "GK600 - panneau de l'écran et de l'éclairage" 'GK600 - screen and lighting panel'
    Prepare $true
    $Panel = Join-Path (Split-Path -Parent $Here) 'panneau\gk600_panel.py'
    if (-not (Test-Path -LiteralPath $Panel)) {
        Fail "panneau\gk600_panel.py est introuvable. Extrais d'abord tout le ZIP (clic droit > Extraire tout), puis relance." `
             'panneau\gk600_panel.py not found. Extract the whole ZIP first (right-click > Extract All), then try again.'
    }
    Say "Le panneau s'ouvre dans une fenêtre à part. Garde cette fenêtre-ci ouverte tant que tu l'utilises : la fermer arrête le panneau." `
        'The panel opens in its own window. Keep this window open while you use it: closing it stops the panel.' 'Yellow'
    exit (Run-Py @($Panel))
}

# ------------------------------------------------------------------ repair
if ($Mode -eq 'repair') {
    Banner "GK600 - réparation des menus et du logo de démarrage de l'écran" 'GK600 - repair the screen menus and boot logo'
    Say "Ça remet les images d'origine (menus, icônes, dragon, animation MSI) depuis la sauvegarde d'un GK600 qui marche. Ton GIF n'est pas touché." `
        'This puts back the original pictures (menus, icons, dragon, MSI animation) from the backup of a working GK600. Your GIF is not touched.'
    Prepare $false

    Step '1/4  Clavier' '1/4  Keyboard'
    Ensure-MsiClosed
    Say "Branche le clavier avec son câble USB, interrupteur sur le mode filaire (USB)." 'Plug the keyboard in with its USB cable, switch set to wired (USB).'
    Wait-Enter 'Appuie sur Entrée' 'Press Enter'
    $fw = Check-Keyboard 3
    Say ('  clavier trouvé, firmware ' + $fw) ('  keyboard found, firmware ' + $fw) 'Green'

    if ($Validated -notcontains $fw) {
        Step 'Test rapide (firmware pas encore testé)' 'Quick test (firmware not tested yet)'
        Say ("Ta version (" + $fw + ") n'a pas encore été testée. On fait d'abord un essai de 3 secondes, sans danger : il raye les icônes de l'écran d'accueil.") `
            ('Your version (' + $fw + ') has not been tested yet. First a 3-second harmless test: it stripes the home-screen icons.') 'Yellow'
        if (-not (Ask-YesNo 'On fait le test ?' 'Run the test?')) { exit 0 }
        Power-Cycle
        if ((Run-Write @('gk600_restore.py', 'probe', '--yes')) -ne 0) { Fail 'Le test a échoué (détails ci-dessus). Ne va pas plus loin.' 'The test failed (details above). Do not go further.' }
        Say "Regarde l'écran d'accueil (appuie sur Verr. Maj pour le redessiner)." 'Look at the home screen (press Caps Lock to redraw it).'
        if (-not (Ask-YesNo 'La batterie et la barre du bas sont-elles rayées magenta et jaune ?' 'Are the battery and the bottom bar striped magenta and yellow?')) {
            Fail ("Arrête-toi là, ne lance pas la réparation. Signale ta version (" + $fw + ") et ce que tu vois sur GitHub (onglet Issues).") `
                 ('Stop here, do not run the repair. Report your version (' + $fw + ') and what you see on GitHub (Issues tab).')
        }
        Say "  test réussi : la réparation va aussi effacer ces rayures" '  test passed: the repair will also clear these stripes' 'Green'
    }

    Step '2/4  Redémarrage du clavier' '2/4  Restart the keyboard'
    Power-Cycle

    Step '3/4  Réparation' '3/4  Repair'
    Say "Ça réécrit les menus et l'animation de démarrage : 960 pages, 2 à 3 minutes." 'It rewrites the menus and the boot animation: 960 pages, 2 to 3 minutes.'
    Say 'Ne débranche rien et ne touche pas au clavier pendant ce temps.' 'Do not unplug anything or touch the keyboard meanwhile.' 'Yellow'
    if (-not (Ask-YesNo 'On y va ?' 'Go?')) { exit 0 }
    if ((Run-Write @('gk600_restore.py', 'restore', '--with-boot', '--yes')) -ne 0) {
        Fail "La réparation s'est arrêtée (détails ci-dessus). Éteins le clavier 10 secondes, rallume-le, puis relance GK600-Repair.bat : elle reprend tout depuis le début." `
             'The repair stopped (details above). Switch the keyboard off for 10 seconds, switch it on, then run GK600-Repair.bat again: it starts over from the beginning.'
    }

    Step '4/4  Vérification' '4/4  Check'
    Say "Terminé ! Éteins le clavier 10 secondes puis rallume-le : l'animation MSI doit se jouer. Parcours ensuite les menus." `
        'Done! Switch the keyboard off for 10 seconds, then on: the MSI animation should play. Then go through the menus.' 'Green'
    Say "Ton GIF revient au redémarrage. Pour éviter que ça recommence : laisse gif_maxframes à 255 dans rgb-keyboard.xml, et 145 images maximum par GIF." `
        'Your GIF comes back after the restart. To keep it from happening again: leave gif_maxframes at 255 in rgb-keyboard.xml, and 145 frames max per GIF.'
    exit 0
}

# ------------------------------------------------------------------ boot animation
if ($Mode -eq 'boot') {
    Banner "GK600 - changer l'animation de démarrage (le logo MSI)" 'GK600 - change the boot animation (the MSI logo)'
    if (-not $Picture) {
        Say "Glisse ton GIF (ou une image PNG / JPG) dans cette fenêtre, puis appuie sur Entrée :" 'Drag your GIF (or a PNG / JPG picture) into this window, then press Enter:'
        $Picture = ([string](Read-Host '>')).Trim().Trim('"')
    }
    if (-not $Picture -or -not (Test-Path -LiteralPath $Picture -PathType Leaf)) {
        Fail ('Fichier introuvable : ' + $Picture) ('File not found: ' + $Picture)
    }
    Say "Écran de 160 x 96 pixels, 72 images au maximum : au-delà, des images sont sautées et la durée totale est gardée. La dernière image reste 1 seconde, puis l'écran d'accueil s'affiche." `
        'Screen of 160 x 96 pixels, 72 frames at most: beyond that, frames are skipped and the total time is kept. The last frame stays 1 second, then the home screen shows.'
    Prepare $true

    Step '1/4  Aperçu' '1/4  Preview'
    Say "L'écriture remet aussi les menus et l'écran d'accueil d'origine. Si tu as mis ta propre image d'accueil, glisse son fichier dans cette fenêtre pour la garder, puis appuie sur Entrée (Entrée seule : le dragon revient) :" `
        'The write also puts back the original menus and home screen. If you set your own home picture, drag its file into this window to keep it, then press Enter (Enter alone: the dragon comes back):'
    $HomePic = ([string](Read-Host '>')).Trim().Trim('"')
    $HomeArgs = @()
    if ($HomePic) {
        if (-not (Test-Path -LiteralPath $HomePic -PathType Leaf)) { Fail ('Image introuvable : ' + $HomePic) ('Picture not found: ' + $HomePic) }
        $HomeArgs = @('--home', $HomePic)
    }
    $Preview = Join-Path $Here 'preview_boot_animation.gif'
    if ((Run-Py (@('gk600_boot_animation.py', $Picture, '--preview', $Preview) + $HomeArgs)) -ne 0) { Fail 'Impossible de lire ce fichier (détails ci-dessus).' 'Cannot read this file (details above).' }
    try { Start-Process -FilePath $Preview } catch { Say ('Aperçu : ' + $Preview) ('Preview: ' + $Preview) }
    if (-not (Ask-YesNo "L'aperçu vient de s'ouvrir. Il commence par une demi-seconde de noir, comme le clavier à l'allumage. On garde cette animation ?" 'The preview just opened. It starts with half a second of black, like the keyboard at power-on. Keep this animation?')) { exit 0 }

    Step '2/4  Clavier' '2/4  Keyboard'
    Ensure-MsiClosed
    Say "Branche le clavier avec son câble USB, interrupteur sur le mode filaire (USB)." 'Plug the keyboard in with its USB cable, switch set to wired (USB).'
    Wait-Enter 'Appuie sur Entrée' 'Press Enter'
    $fw = Check-Keyboard 3
    Say ('  clavier trouvé, firmware ' + $fw) ('  keyboard found, firmware ' + $fw) 'Green'
    if ($Validated -notcontains $fw) {
        Fail ("L'animation de démarrage n'est prévue que pour les firmwares V1.04 et V1.20 (le tien : " + $fw + "). Lance d'abord GK600-Repair.bat, qui teste ta version, et signale le résultat sur GitHub (onglet Issues).") `
             ('The boot animation is only meant for firmware V1.04 and V1.20 (yours: ' + $fw + '). Run GK600-Repair.bat first, which tests your version, and report the result on GitHub (Issues tab).')
    }

    Step '3/4  Redémarrage du clavier' '3/4  Restart the keyboard'
    Power-Cycle

    Step '4/4  Écriture' '4/4  Write'
    Say "Ça réécrit le début de la mémoire de l'écran avec ton animation : jusqu'à 957 pages, 1 à 3 minutes." `
        'It rewrites the start of the screen memory with your animation: up to 957 pages, 1 to 3 minutes.'
    Say 'Ne débranche rien pendant ce temps.' 'Do not unplug anything meanwhile.' 'Yellow'
    if (-not (Ask-YesNo 'On y va ?' 'Go?')) { exit 0 }
    if ((Run-Write (@('gk600_boot_animation.py', $Picture, '--yes') + $HomeArgs)) -ne 0) {
        Fail "L'écriture s'est arrêtée (détails ci-dessus). Éteins le clavier 10 secondes, rallume-le, puis relance : elle reprend depuis le début." `
             'The write stopped (details above). Switch the keyboard off for 10 seconds, switch it on, then run it again: it starts over from the beginning.'
    }
    Say "Terminé ! Éteins le clavier puis rallume-le : ton animation se joue au démarrage. Pour remettre l'animation MSI (et le dragon) : GK600-Repair.bat." `
        'Done! Switch the keyboard off and on: your animation plays at power-on. To put the MSI animation (and the dragon) back: GK600-Repair.bat.' 'Green'
    exit 0
}

# ------------------------------------------------------------------ home-screen picture
Banner "GK600 - changer l'image de l'écran d'accueil (le dragon)" 'GK600 - change the home-screen picture (the dragon)'
if (-not $Picture) {
    Say "Glisse ton image (PNG ou JPG) dans cette fenêtre, puis appuie sur Entrée :" 'Drag your picture (PNG or JPG) into this window, then press Enter:'
    $Picture = ([string](Read-Host '>')).Trim().Trim('"')
}
if (-not $Picture -or -not (Test-Path -LiteralPath $Picture -PathType Leaf)) {
    Fail ('Image introuvable : ' + $Picture) ('Picture not found: ' + $Picture)
}
Say ("Zone affichée : 160 x 65 pixels en haut de l'écran. L'image est réduite pour y tenir, sur fond noir. La batterie s'affiche par-dessus le coin en haut à droite.") `
    'Shown area: 160 x 65 pixels at the top of the screen. The picture is scaled down to fit, on black. The battery is drawn over the top-right corner.'
Prepare $true

Step '1/4  Aperçu' '1/4  Preview'
$Preview = Join-Path $Here 'preview_home_screen.png'
if ((Run-Py @('gk600_home_picture.py', $Picture, '--preview', $Preview)) -ne 0) { Fail "Impossible de lire cette image (détails ci-dessus)." 'Cannot read this picture (details above).' }
try { Start-Process -FilePath $Preview } catch { Say ('Aperçu : ' + $Preview) ('Preview: ' + $Preview) }
if (-not (Ask-YesNo "L'aperçu de l'écran d'accueil vient de s'ouvrir. On garde cette image ?" 'The home-screen preview just opened. Keep this picture?')) { exit 0 }

Step '2/4  Clavier' '2/4  Keyboard'
Ensure-MsiClosed
Say "Branche le clavier avec son câble USB, interrupteur sur le mode filaire (USB)." 'Plug the keyboard in with its USB cable, switch set to wired (USB).'
Wait-Enter 'Appuie sur Entrée' 'Press Enter'
$fw = Check-Keyboard 3
Say ('  clavier trouvé, firmware ' + $fw) ('  keyboard found, firmware ' + $fw) 'Green'
if ($Validated -notcontains $fw) {
    Fail ("L'image d'accueil n'est validée qu'en firmware V1.04 et V1.20 (le tien : " + $fw + "). Lance d'abord GK600-Repair.bat, qui teste ta version, et signale le résultat sur GitHub (onglet Issues).") `
         ('The home picture is only validated on firmware V1.04 and V1.20 (yours: ' + $fw + '). Run GK600-Repair.bat first, which tests your version, and report the result on GitHub (Issues tab).')
}

Step '3/4  Redémarrage du clavier' '3/4  Restart the keyboard'
Power-Cycle

Step '4/4  Écriture' '4/4  Write'
Say "Ça réécrit le début de la mémoire de l'écran avec ton image à la place du dragon : 384 pages, environ 1 minute." `
    "It rewrites the start of the screen memory with your picture in place of the dragon: 384 pages, about 1 minute."
Say 'Ne débranche rien pendant ce temps.' 'Do not unplug anything meanwhile.' 'Yellow'
if (-not (Ask-YesNo 'On y va ?' 'Go?')) { exit 0 }
if ((Run-Write @('gk600_home_picture.py', $Picture, '--yes')) -ne 0) {
    Fail "L'écriture s'est arrêtée (détails ci-dessus). Éteins le clavier 10 secondes, rallume-le, puis relance : elle reprend depuis le début." `
         'The write stopped (details above). Switch the keyboard off for 10 seconds, switch it on, then run it again: it starts over from the beginning.'
}
Say "Terminé ! Ton image est sur l'écran d'accueil. Pour remettre le dragon d'origine : GK600-Repair.bat." `
    'Done! Your picture is on the home screen. To put the original dragon back: GK600-Repair.bat.' 'Green'
exit 0
