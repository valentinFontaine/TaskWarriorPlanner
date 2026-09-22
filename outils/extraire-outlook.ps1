<#
.SYNOPSIS
    Extrait l'agenda Outlook vers reunions.json. LECTURE SEULE.

.DESCRIPTION
    Recopie ce qu'Outlook dit, sans rien filtrer et sans rien interpreter. Tout
    le tri (qui occupe reellement du temps, qui est dans la fenetre) vit dans
    planif/reunions.py, ou il se teste sans Outlook. Changer une regle de
    filtrage ne doit jamais obliger a relancer ce script.

    Ce script n'ECRIT RIEN dans Outlook. Il ouvre l'application si elle est
    fermee, lit le calendrier par defaut, et la laisse ouverte.

.NOTES
    LE PIEGE A CONNAITRE -- la locale.

    Items.Restrict() attend ses dates dans le format court de la MACHINE. Sur un
    Windows en francais, "09/22/2026" ne leve aucune erreur : le filtre rend
    simplement ZERO evenement, en silence. C'est ainsi qu'on peut conclure « ton
    agenda est vide » sur un calendrier qui contient 1464 entrees.
    D'ou ToString("dd/MM/yyyy HH:mm") ici, et la verification de vraisemblance
    en fin de script.

    LES OCCURRENCES RECURRENTES PARTAGENT L'EntryID DE LEUR SERIE. Sur un export
    reel : 18 occurrences, 6 EntryID. Ne jamais dedupliquer la-dessus.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File outils\extraire-outlook.ps1
    powershell -ExecutionPolicy Bypass -File outils\extraire-outlook.ps1 -Semaines 12
#>
param(
    [int]$Semaines = 6,
    [string]$Sortie = "reunions.json"
)

$ErrorActionPreference = "Stop"

$outlook = New-Object -ComObject Outlook.Application
$espace  = $outlook.GetNamespace("MAPI")
$calendrier = $espace.GetDefaultFolder(9)   # olFolderCalendar

$total = $calendrier.Items.Count
Write-Host "calendrier : $($calendrier.Name) ($($calendrier.Store.DisplayName)), $total entrees au total"

$items = $calendrier.Items
$items.IncludeRecurrences = $true            # sinon on ne voit que les series, pas leurs occurrences
$items.Sort("[Start]")                       # obligatoire avec IncludeRecurrences

$debut = (Get-Date).Date
$fin   = $debut.AddDays($Semaines * 7)

# Format court de la machine : voir la note sur la locale en tete de fichier.
$filtre = "[Start] >= '" + $debut.ToString("dd/MM/yyyy HH:mm") + "' AND [Start] < '" + $fin.ToString("dd/MM/yyyy HH:mm") + "'"
$selection = $items.Restrict($filtre)

$evenements = @()
foreach ($i in $selection) {
    $evenements += [PSCustomObject]@{
        entryId        = $i.EntryID          # celui de la SERIE pour un recurrent
        sujet          = $i.Subject
        debut          = $i.Start.ToString("s")
        fin            = $i.End.ToString("s")
        dureeMin       = [int]($i.End - $i.Start).TotalMinutes
        journeeEntiere = $i.AllDayEvent
        occupation     = $i.BusyStatus       # 0 Free, 1 Tentative, 2 Busy, 3 OutOfOffice
        reponse        = $i.ResponseStatus   # 4 = Declined
        recurrent      = $i.IsRecurring
        lieu           = $i.Location
    }
}

if ($evenements.Count -eq 0 -and $total -gt 0) {
    Write-Warning "ZERO evenement extrait alors que le calendrier en contient $total."
    Write-Warning "C'est le symptome du piege de locale : Restrict() a recu un format"
    Write-Warning "de date que cette machine ne comprend pas, et n'a rien dit."
    Write-Warning "Filtre utilise : $filtre"
    exit 1
}

$evenements | ConvertTo-Json -Depth 3 | Out-File -FilePath $Sortie -Encoding utf8

$series = ($evenements | Select-Object -ExpandProperty entryId | Sort-Object -Unique).Count
Write-Host "fenetre  : $($debut.ToString('yyyy-MM-dd')) -> $($fin.ToString('yyyy-MM-dd')) ($Semaines semaines)"
Write-Host "extraits : $($evenements.Count) evenements, $series series distinctes"
Write-Host "ecrit    : $Sortie"
Write-Host ""
Write-Host "Ce fichier porte vos sujets et vos lieux reels : il est ignore par git."
