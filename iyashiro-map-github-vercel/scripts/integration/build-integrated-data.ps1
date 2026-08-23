[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$R3Bundle,
    [Parameter(Mandatory = $true)]
    [string]$OrbitDistances,
    [Parameter(Mandatory = $true)]
    [string]$OrbitFacilities,
    [Parameter(Mandatory = $true)]
    [string]$OrbitVerification,
    [string]$OutputRoot = (Join-Path $PSScriptRoot "..\..\public\data\integrated")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ReleaseId = "iyashiro-r3-orbit-v2-20260823"
$SchemaVersion = "iyashiro-integrated-data/1.0"
$ExpectedCellCount = 120662
$ExpectedDistanceCount = 482648
$ExpectedFacilityCount = 31544
$ExpectedLensCount = 84060
$ExpectedPassCount = 20118
$ExpectedCategories = @("temple", "shrine", "cemetery", "hospital")
$ExpectedR3Header = @(
    "Cell ID", "Row", "Col", "Municipality", "Town", "Latitude", "Longitude",
    "V15 Rank", "V15 Zone", "V15 Regime", "RY Rank", "RY Zone", "RY Area",
    "RY Confidence", "RY Current Water", "RY Hard Split", "Spiritual Pass",
    "650m Core", "Fail Reasons", "Integrated Cell Score", "Lens Score",
    "Min Margin m", "Temple m", "Cemetery m", "Large Hospital m",
    "Large Hospital", "Beds", "Strong History Effective m", "Strong History Raw m",
    "History Proxy m", "Nearest Strong History", "History Category", "P8 Min m",
    "P8 Within500", "Moisture", "Groundwater Band", "JSHIS Risk", "JSHIS Detail",
    "Wet History", "P7 Known Eras", "P7 State", "EVENTREG Fatalities",
    "EVENTREG 500m", "VEIL 500m Count", "VEIL State", "ECOSCAPE State",
    "ECOSCAPE Tier", "PLACEGRAPH Status", "Identity Conflicts", "Source URL V15",
    "Source URL RY", "Source URL ORBIT", "Source URL History"
)
$PublicR3RedactedFields = [Collections.Generic.HashSet[string]]::new(
    [string[]]@(
        "Source URL V15", "Source URL RY", "Source URL ORBIT",
        "Source URL History"
    )
)
$ExpectedPublicR3SourcePointerCount = $ExpectedLensCount * $PublicR3RedactedFields.Count
$ExpectedDistanceHeader = @(
    "cell_id", "grid_index", "cell_index", "municipality_index", "latitude",
    "longitude", "category", "distance_m", "nearest_facility_id", "nearest_name",
    "nearest_address", "geometry_basis"
)
$ExpectedFacilityHeader = @(
    "facility_id", "categories", "primary_category", "subtype", "name",
    "name_normalized", "aliases", "address", "address_normalized", "latitude",
    "longitude", "geometry_type", "geometry_basis", "crs", "source_authority",
    "source_dataset", "source_record_id", "source_url", "source_snapshot_date",
    "source_license", "coordinate_accuracy", "record_status", "in_primary_scope",
    "buffer_only", "municipality_index", "total_beds",
    "large_inpatient_hospital", "source_link_count"
)

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}

function Get-Sha256File {
    param([string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Get-Sha256Bytes {
    param([byte[]]$Bytes)
    return [Convert]::ToHexString(
        [Security.Cryptography.SHA256]::HashData($Bytes)
    ).ToLowerInvariant()
}

function Get-FileArtifact {
    param([string]$Root, [string]$Path)
    $item = Get-Item -LiteralPath $Path
    return [ordered]@{
        path = [IO.Path]::GetRelativePath($Root, $Path).Replace("\", "/")
        bytes = $item.Length
        sha256 = Get-Sha256File $Path
    }
}

function Read-ZipEntryBytes {
    param([string]$ZipPath, [string]$EntryName)
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [IO.Compression.ZipFile]::OpenRead($ZipPath)
    try {
        $entry = $zip.Entries | Where-Object FullName -eq $EntryName
        Assert-True ($null -ne $entry) "Missing ZIP entry: $EntryName"
        $memory = [IO.MemoryStream]::new()
        try {
            $stream = $entry.Open()
            try { $stream.CopyTo($memory) } finally { $stream.Dispose() }
            return ,$memory.ToArray()
        } finally {
            $memory.Dispose()
        }
    } finally {
        $zip.Dispose()
    }
}

function Read-ZipText {
    param([string]$ZipPath, [string]$EntryName)
    $bytes = Read-ZipEntryBytes $ZipPath $EntryName
    return [Text.Encoding]::UTF8.GetString($bytes)
}

function New-GzipCsvParserFromBytes {
    param([byte[]]$Bytes)
    $memory = [IO.MemoryStream]::new($Bytes, $false)
    $gzip = [IO.Compression.GzipStream]::new(
        $memory,
        [IO.Compression.CompressionMode]::Decompress
    )
    $parser = [Microsoft.VisualBasic.FileIO.TextFieldParser]::new(
        $gzip,
        [Text.Encoding]::UTF8,
        $true
    )
    $parser.TextFieldType = [Microsoft.VisualBasic.FileIO.FieldType]::Delimited
    $parser.SetDelimiters(",")
    $parser.HasFieldsEnclosedInQuotes = $true
    return $parser
}

function New-GzipCsvParserFromFile {
    param([string]$Path)
    $file = [IO.File]::OpenRead($Path)
    $gzip = [IO.Compression.GzipStream]::new(
        $file,
        [IO.Compression.CompressionMode]::Decompress
    )
    $parser = [Microsoft.VisualBasic.FileIO.TextFieldParser]::new(
        $gzip,
        [Text.Encoding]::UTF8,
        $true
    )
    $parser.TextFieldType = [Microsoft.VisualBasic.FileIO.FieldType]::Delimited
    $parser.SetDelimiters(",")
    $parser.HasFieldsEnclosedInQuotes = $true
    return $parser
}

function Assert-Header {
    param([string[]]$Actual, [string[]]$Expected, [string]$Label)
    Assert-True ($Actual.Count -eq $Expected.Count) "$Label header width changed."
    for ($index = 0; $index -lt $Expected.Count; $index++) {
        Assert-True ($Actual[$index] -ceq $Expected[$index]) (
            "$Label header mismatch at $index. Expected '$($Expected[$index])', got '$($Actual[$index])'."
        )
    }
}

function Get-NullableString {
    param([string]$Value)
    if ([string]::IsNullOrEmpty($Value)) { return $null }
    return $Value
}

function Get-NullableDouble {
    param([string]$Value)
    if ([string]::IsNullOrEmpty($Value)) { return $null }
    return [double]::Parse($Value, [Globalization.CultureInfo]::InvariantCulture)
}

function Get-NullableInt {
    param([string]$Value)
    if ([string]::IsNullOrEmpty($Value)) { return $null }
    return [int]::Parse($Value, [Globalization.CultureInfo]::InvariantCulture)
}

function Get-NullableBool {
    param([string]$Value)
    if ([string]::IsNullOrEmpty($Value)) { return $null }
    if ($Value -ceq "True" -or $Value -ceq "true") { return $true }
    if ($Value -ceq "False" -or $Value -ceq "false") { return $false }
    throw "Invalid boolean '$Value'."
}

$R3IntegerFields = [Collections.Generic.HashSet[string]]::new(
    [string[]]@(
        "Row", "Col", "V15 Rank", "RY Rank", "Beds", "P8 Within500",
        "P7 Known Eras", "EVENTREG Fatalities", "EVENTREG 500m",
        "VEIL 500m Count", "Identity Conflicts"
    )
)
$R3DoubleFields = [Collections.Generic.HashSet[string]]::new(
    [string[]]@(
        "Latitude", "Longitude", "Integrated Cell Score", "Lens Score",
        "Min Margin m", "Temple m", "Cemetery m", "Large Hospital m",
        "Strong History Effective m", "Strong History Raw m", "History Proxy m",
        "P8 Min m", "JSHIS Risk"
    )
)
$R3BooleanFields = [Collections.Generic.HashSet[string]]::new(
    [string[]]@("Spiritual Pass", "650m Core", "Wet History")
)

function Convert-R3Value {
    param([string]$Name, [string]$Value)
    if ($Name -ceq "Fail Reasons") {
        if ([string]::IsNullOrEmpty($Value)) { return ,@() }
        return ,@($Value -split "/" | ForEach-Object { $_.Trim() } | Where-Object { $_ })
    }
    if ($R3IntegerFields.Contains($Name)) { return Get-NullableInt $Value }
    if ($R3DoubleFields.Contains($Name)) { return Get-NullableDouble $Value }
    if ($R3BooleanFields.Contains($Name)) { return Get-NullableBool $Value }
    return Get-NullableString $Value
}

function Convert-FacilityValue {
    param([string]$Name, [string]$Value)
    if ($Name -in @("latitude", "longitude")) { return Get-NullableDouble $Value }
    if ($Name -in @("municipality_index", "total_beds", "source_link_count")) {
        return Get-NullableInt $Value
    }
    if ($Name -in @("in_primary_scope", "buffer_only", "large_inpatient_hospital")) {
        return Get-NullableBool $Value
    }
    return Get-NullableString $Value
}

function Convert-ToCompactJson {
    param([object]$Value, [int]$Depth = 30)
    return ConvertTo-Json -InputObject $Value -Compress -Depth $Depth
}

function Parse-CellId {
    param([string]$CellId)
    $match = [regex]::Match($CellId, "^g([0-9]+)-([0-9]+)$")
    Assert-True $match.Success "Invalid canonical cell ID: $CellId"
    return [int[]]@(
        [int]::Parse($match.Groups[1].Value),
        [int]::Parse($match.Groups[2].Value)
    )
}

function Open-Utf8Writer {
    param([string]$Path)
    return [IO.StreamWriter]::new(
        $Path,
        $false,
        [Text.UTF8Encoding]::new($false)
    )
}

foreach ($source in @($R3Bundle, $OrbitDistances, $OrbitFacilities, $OrbitVerification)) {
    Assert-True (Test-Path -LiteralPath $source -PathType Leaf) "Missing source file: $source"
}
if (Test-Path -LiteralPath $OutputRoot) {
    $blockingOutput = @(
        Get-ChildItem -LiteralPath $OutputRoot -Force |
            Where-Object Name -notlike "__partial_failed_*"
    )
    Assert-True ($blockingOutput.Count -eq 0) (
        "Output contains non-quarantined files. Refusing overwrite: $OutputRoot"
    )
}

$rowsDirectory = Join-Path $OutputRoot "rows"
$facilitiesDirectory = Join-Path $OutputRoot "facilities"
[IO.Directory]::CreateDirectory($rowsDirectory) | Out-Null
[IO.Directory]::CreateDirectory($facilitiesDirectory) | Out-Null

$workDirectory = Join-Path ([IO.Path]::GetTempPath()) (
    "iyashiro-integrated-" + [guid]::NewGuid().ToString("N")
)
$r3WorkDirectory = Join-Path $workDirectory "r3"
$facilityWorkDirectory = Join-Path $workDirectory "facilities"
[IO.Directory]::CreateDirectory($r3WorkDirectory) | Out-Null
[IO.Directory]::CreateDirectory($facilityWorkDirectory) | Out-Null

try {
    $r3Manifest = Read-ZipText $R3Bundle "MANIFEST.json" | ConvertFrom-Json
    Assert-True ($r3Manifest.authorities.canonical_cells -eq $ExpectedCellCount) (
        "R3 canonical cell authority changed."
    )
    Assert-True ($r3Manifest.counts.either_lens_cells -eq $ExpectedLensCount) (
        "R3 lens count changed."
    )
    Assert-True ($r3Manifest.counts.r3_pass_lens_cells -eq $ExpectedPassCount) (
        "R3 pass count changed."
    )

    $allLensBytes = Read-ZipEntryBytes $R3Bundle "data/ALL_LENS_CELL_LEDGER_84060.csv.gz"
    $passBytes = Read-ZipEntryBytes $R3Bundle "data/SPIRITUAL_PASS_CELL_LEDGER.csv.gz"
    $allLensManifestArtifact = $r3Manifest.artifacts |
        Where-Object name -eq "ALL_LENS_CELL_LEDGER_84060.csv.gz" |
        Select-Object -First 1
    $passManifestArtifact = $r3Manifest.artifacts |
        Where-Object name -eq "SPIRITUAL_PASS_CELL_LEDGER.csv.gz" |
        Select-Object -First 1
    Assert-True ($null -ne $allLensManifestArtifact) "R3 all-lens artifact is absent from MANIFEST."
    Assert-True ($null -ne $passManifestArtifact) "R3 pass artifact is absent from MANIFEST."
    Assert-True ((Get-Sha256Bytes $allLensBytes) -ceq $allLensManifestArtifact.sha256) (
        "R3 all-lens SHA-256 mismatch."
    )
    Assert-True ((Get-Sha256Bytes $passBytes) -ceq $passManifestArtifact.sha256) (
        "R3 pass SHA-256 mismatch."
    )

    $orbitVerificationData = Get-Content -LiteralPath $OrbitVerification -Raw -Encoding UTF8 |
        ConvertFrom-Json
    $distanceFileName = [IO.Path]::GetFileName($OrbitDistances)
    $facilityFileName = [IO.Path]::GetFileName($OrbitFacilities)
    $expectedDistanceHash = $orbitVerificationData.artifacts.$distanceFileName.sha256
    $expectedFacilityHash = $orbitVerificationData.artifacts.$facilityFileName.sha256
    Assert-True ((Get-Sha256File $OrbitDistances) -ceq $expectedDistanceHash) (
        "ORBIT distance SHA-256 mismatch."
    )
    Assert-True ((Get-Sha256File $OrbitFacilities) -ceq $expectedFacilityHash) (
        "ORBIT facility SHA-256 mismatch."
    )

    $passSet = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    $passParser = New-GzipCsvParserFromBytes $passBytes
    try {
        $header = $passParser.ReadFields()
        Assert-Header $header $ExpectedR3Header "R3 pass ledger"
        while (-not $passParser.EndOfData) {
            $fields = $passParser.ReadFields()
            Assert-True ($fields.Count -eq $ExpectedR3Header.Count) "Malformed R3 pass row."
            $cellId = $fields[0]
            Assert-True ($passSet.Add($cellId)) "Duplicate R3 pass cell: $cellId"
            Assert-True ((Get-NullableBool $fields[16]) -eq $true) (
                "Pass ledger contains a non-pass row: $cellId"
            )
        }
    } finally {
        $passParser.Dispose()
    }
    Assert-True ($passSet.Count -eq $ExpectedPassCount) "R3 pass ledger count mismatch."

    $r3Writers = @{}
    $r3CellSet = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    $r3PassFlagCount = 0
    $r3PassSeen = 0
    $r3SourcePointerValuesRedacted = 0
    try {
        $r3Parser = New-GzipCsvParserFromBytes $allLensBytes
        try {
            $header = $r3Parser.ReadFields()
            Assert-Header $header $ExpectedR3Header "R3 all-lens ledger"
            while (-not $r3Parser.EndOfData) {
                $fields = $r3Parser.ReadFields()
                Assert-True ($fields.Count -eq $ExpectedR3Header.Count) "Malformed R3 all-lens row."
                $cellId = $fields[0]
                Assert-True ($r3CellSet.Add($cellId)) "Duplicate R3 lens cell: $cellId"
                $parts = Parse-CellId $cellId
                $rowKey = $parts[0].ToString("000")
                if (-not $r3Writers.ContainsKey($rowKey)) {
                    $r3Writers[$rowKey] = Open-Utf8Writer (
                        Join-Path $r3WorkDirectory ("g" + $rowKey + ".ndjson")
                    )
                }
                $tuple = [object[]]::new($ExpectedR3Header.Count - 1)
                for ($index = 1; $index -lt $ExpectedR3Header.Count; $index++) {
                    $fieldName = $ExpectedR3Header[$index]
                    if ($PublicR3RedactedFields.Contains($fieldName)) {
                        if (-not [string]::IsNullOrEmpty($fields[$index])) {
                            $r3SourcePointerValuesRedacted++
                        }
                        $tuple[$index - 1] = $null
                    } else {
                        $tuple[$index - 1] = Convert-R3Value $fieldName $fields[$index]
                    }
                }
                $isPass = $tuple[15]
                if ($isPass -eq $true) { $r3PassFlagCount++ }
                $inPassLedger = $passSet.Contains($cellId)
                Assert-True (($isPass -eq $true) -eq $inPassLedger) (
                    "R3 pass ledgers disagree for $cellId."
                )
                if ($inPassLedger) { $r3PassSeen++ }
                $r3Writers[$rowKey].WriteLine(
                    $cellId + [char]9 + (Convert-ToCompactJson $tuple)
                )
            }
        } finally {
            $r3Parser.Dispose()
        }
    } finally {
        foreach ($writer in $r3Writers.Values) { $writer.Dispose() }
    }
    Assert-True ($r3CellSet.Count -eq $ExpectedLensCount) "R3 all-lens count mismatch."
    Assert-True ($r3PassFlagCount -eq $ExpectedPassCount) "R3 pass flag count mismatch."
    Assert-True ($r3PassSeen -eq $ExpectedPassCount) "R3 pass set was not fully matched."
    Assert-True ($r3SourcePointerValuesRedacted -eq $ExpectedPublicR3SourcePointerCount) (
        "R3 public source-pointer redaction count mismatch."
    )

    $facilitySet = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    $facilitySummary = [Collections.Generic.Dictionary[string, object]]::new(
        [StringComparer]::Ordinal
    )
    $facilityCategoryCounts = [ordered]@{
        temple = 0
        shrine = 0
        cemetery = 0
        hospital = 0
    }
    $largeHospitalCount = 0
    $facilityWriters = @{}
    try {
        $facilityParser = New-GzipCsvParserFromFile $OrbitFacilities
        try {
            $header = $facilityParser.ReadFields()
            Assert-Header $header $ExpectedFacilityHeader "ORBIT facility ledger"
            while (-not $facilityParser.EndOfData) {
                $fields = $facilityParser.ReadFields()
                Assert-True ($fields.Count -eq $ExpectedFacilityHeader.Count) (
                    "Malformed ORBIT facility row."
                )
                $facilityId = $fields[0]
                Assert-True ($facilitySet.Add($facilityId)) (
                    "Duplicate ORBIT facility ID: $facilityId"
                )
                foreach ($category in ($fields[1] -split "[|;]")) {
                    if ($facilityCategoryCounts.Contains($category)) {
                        $facilityCategoryCounts[$category]++
                    }
                }
                $large = Get-NullableBool $fields[26]
                if ($large -eq $true) { $largeHospitalCount++ }
                $facilitySummary.Add(
                    $facilityId,
                    [object[]]@(
                        (Get-NullableString $fields[2]),
                        (Get-NullableString $fields[4]),
                        (Get-NullableString $fields[7]),
                        (Get-NullableInt $fields[25]),
                        $large
                    )
                )
                $tuple = [object[]]::new($ExpectedFacilityHeader.Count)
                for ($index = 0; $index -lt $ExpectedFacilityHeader.Count; $index++) {
                    $tuple[$index] = Convert-FacilityValue $ExpectedFacilityHeader[$index] $fields[$index]
                }
                $idHash = [Security.Cryptography.SHA256]::HashData(
                    [Text.Encoding]::UTF8.GetBytes($facilityId)
                )
                $shard = $idHash[0].ToString("x2").Substring(0, 1)
                if (-not $facilityWriters.ContainsKey($shard)) {
                    $facilityWriters[$shard] = Open-Utf8Writer (
                        Join-Path $facilityWorkDirectory ("part-" + $shard + ".ndjson")
                    )
                }
                $facilityWriters[$shard].WriteLine((Convert-ToCompactJson $tuple))
            }
        } finally {
            $facilityParser.Dispose()
        }
    } finally {
        foreach ($writer in $facilityWriters.Values) { $writer.Dispose() }
    }
    Assert-True ($facilitySet.Count -eq $ExpectedFacilityCount) (
        "ORBIT canonical facility count mismatch."
    )
    foreach ($category in $ExpectedCategories) {
        $expected = [int]$orbitVerificationData.counts.byCategoryDistanceUniverse.$category
        Assert-True ($facilityCategoryCounts[$category] -eq $expected) (
            "ORBIT facility category count mismatch for $category."
        )
    }

    $artifactList = [Collections.Generic.List[object]]::new()
    $facilityArtifactList = [Collections.Generic.List[object]]::new()
    foreach ($shard in @("0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "a", "b", "c", "d", "e", "f")) {
        $inputPath = Join-Path $facilityWorkDirectory ("part-" + $shard + ".ndjson")
        $outputPath = Join-Path $facilitiesDirectory ("part-" + $shard + ".json")
        $writer = Open-Utf8Writer $outputPath
        try {
            $writer.Write(
                '{"schemaVersion":"' + $SchemaVersion +
                '","releaseId":"' + $ReleaseId +
                '","shard":"' + $shard + '","facilities":['
            )
            $first = $true
            if (Test-Path -LiteralPath $inputPath) {
                $reader = [IO.StreamReader]::new($inputPath, [Text.Encoding]::UTF8)
                try {
                    while (-not $reader.EndOfStream) {
                        if (-not $first) { $writer.Write(",") }
                        $writer.Write($reader.ReadLine())
                        $first = $false
                    }
                } finally {
                    $reader.Dispose()
                }
            }
            $writer.Write("]}")
        } finally {
            $writer.Dispose()
        }
        $artifact = Get-FileArtifact $OutputRoot $outputPath
        $facilityArtifactList.Add($artifact)
        $artifactList.Add($artifact)
    }

    $r3Fields = @($ExpectedR3Header | Select-Object -Skip 1)
    $schema = [ordered]@{
        schemaVersion = $SchemaVersion
        releaseId = $ReleaseId
        canonicalGrid = [ordered]@{
            cellIdPattern = "^g([0-9]+)-([0-9]+)$"
            rows = 624
            columns = 462
            crs = "EPSG:6668"
        }
        cellTuple = @(
            "cellId", "gridColumn", "latitude", "longitude", "municipalityIndex",
            "temple", "shrine", "cemetery", "hospital", "r3"
        )
        distanceTuple = @(
            "distanceM", "nearestFacilityId", "nearestName", "nearestAddress",
            "geometryBasis", "beds", "largeInpatientHospital", "primaryCategory"
        )
        r3Tuple = $r3Fields
        facilityTuple = $ExpectedFacilityHeader
        semantics = [ordered]@{
            unknownIsSafe = $false
            shrine = "context_only"
            generalHospital = "excluded_from_ranking"
            templeThresholdM = 500
            cemeteryThresholdM = 500
            largeInpatientHospitalThresholdM = 500
            strongHistoryEffectiveThresholdM = 500
            p8LocatedContextThresholdM = 500
            cemeteryCoverage = "UNKNOWN_REQUEST_REQUIRED_FOR_FULL_PERMIT_LEDGER"
            templeCoverage = "OSM_SNAPSHOT_COMPLETE_OFFICIAL_SITE_LINKAGE_PARTIAL"
            shrineCoverage = "OSM_SNAPSHOT_COMPLETE_OFFICIAL_SITE_LINKAGE_PARTIAL"
            r3SourcePointers = "REDACTED_FROM_PUBLIC_RUNTIME"
        }
    }
    $schemaPath = Join-Path $OutputRoot "schema.json"
    [IO.File]::WriteAllText(
        $schemaPath,
        (Convert-ToCompactJson $schema 50),
        [Text.UTF8Encoding]::new($false)
    )
    $artifactList.Add((Get-FileArtifact $OutputRoot $schemaPath))

    function Read-R3RowMap {
        param([int]$Row)
        $map = [Collections.Generic.Dictionary[string, object]]::new(
            [StringComparer]::Ordinal
        )
        $path = Join-Path $r3WorkDirectory ("g" + $Row.ToString("000") + ".ndjson")
        if (-not (Test-Path -LiteralPath $path)) { return ,$map }
        $reader = [IO.StreamReader]::new($path, [Text.Encoding]::UTF8)
        try {
            while (-not $reader.EndOfStream) {
                $line = $reader.ReadLine()
                $tab = $line.IndexOf([char]9)
                Assert-True ($tab -gt 0) "Malformed R3 partition line."
                $cellId = $line.Substring(0, $tab)
                $tuple = ConvertFrom-Json -InputObject $line.Substring($tab + 1) -NoEnumerate
                $map.Add($cellId, $tuple)
            }
        } finally {
            $reader.Dispose()
        }
        return ,$map
    }

    $rowArtifacts = [Collections.Generic.List[object]]::new()
    $rowCells = [Collections.Generic.List[object]]::new()
    $currentOutputRow = -1
    $currentR3Map = $null
    $r3AttachedCount = 0
    $noLensSample = $null
    $knownPassSample = $null
    $knownFailSample = $null
    $maxR3CoordinateDelta = 0.0
    $maxTempleDelta = 0.0
    $maxCemeteryDelta = 0.0

    $flushRow = {
        if ($currentOutputRow -ge 0) {
            Assert-True ($currentR3Map.Count -eq 0) (
                "R3 cells were not found in ORBIT row g$($currentOutputRow): " +
                (($currentR3Map.Keys | Select-Object -First 3) -join ",")
            )
            $path = Join-Path $rowsDirectory (
                "g" + $currentOutputRow.ToString("000") + ".json"
            )
            $payload = [ordered]@{
                schemaVersion = $SchemaVersion
                releaseId = $ReleaseId
                gridRow = $currentOutputRow
                cells = $rowCells.ToArray()
            }
            [IO.File]::WriteAllText(
                $path,
                (Convert-ToCompactJson $payload 60),
                [Text.UTF8Encoding]::new($false)
            )
            $artifact = Get-FileArtifact $OutputRoot $path
            $rowArtifacts.Add($artifact)
            $artifactList.Add($artifact)
            $rowCells = [Collections.Generic.List[object]]::new()
        }
    }

    $distanceCategoryCounts = [ordered]@{
        temple = 0
        shrine = 0
        cemetery = 0
        hospital = 0
    }
    $distanceRows = 0
    $cellCount = 0
    $missingFacilityReferences = 0
    $previousCompletedGridIndex = -1
    $currentCellId = $null
    $currentGridIndex = -1
    $currentMunicipalityIndex = $null
    $currentLatitude = $null
    $currentLongitude = $null
    $currentFacts = @{}

    $completeCell = {
        Assert-True ($null -ne $currentCellId) "Cannot complete a null ORBIT cell."
        Assert-True ($currentFacts.Count -eq 4) (
            "Cell $currentCellId does not have exactly four ORBIT categories."
        )
        foreach ($category in $ExpectedCategories) {
            Assert-True $currentFacts.ContainsKey($category) (
                "Cell $currentCellId is missing ORBIT category $category."
            )
        }
        Assert-True ($currentGridIndex -gt $previousCompletedGridIndex) (
            "ORBIT cell order is not strictly increasing at $currentCellId."
        )
        $parts = Parse-CellId $currentCellId
        $gridRow = $parts[0]
        $gridColumn = $parts[1]
        Assert-True ($currentGridIndex -eq ($gridRow * 462 + $gridColumn)) (
            "ORBIT grid_index disagrees with cell_id for $currentCellId."
        )

        if ($gridRow -ne $currentOutputRow) {
            . $flushRow
            $currentOutputRow = $gridRow
            $currentR3Map = Read-R3RowMap $gridRow
        }

        $r3Tuple = $null
        $r3Candidate = $null
        if ($currentR3Map.TryGetValue($currentCellId, [ref]$r3Candidate)) {
            $r3Tuple = $r3Candidate
            $currentR3Map.Remove($currentCellId) | Out-Null
            $r3AttachedCount++
            $latDelta = [Math]::Abs(
                [double]$r3Tuple[4] - [double]$currentLatitude
            )
            $lonDelta = [Math]::Abs(
                [double]$r3Tuple[5] - [double]$currentLongitude
            )
            $maxR3CoordinateDelta = [Math]::Max(
                $maxR3CoordinateDelta,
                [Math]::Max($latDelta, $lonDelta)
            )
            if ($null -ne $r3Tuple[21]) {
                $maxTempleDelta = [Math]::Max(
                    $maxTempleDelta,
                    [Math]::Abs([double]$r3Tuple[21] - [double]$currentFacts.temple[0])
                )
            }
            if ($null -ne $r3Tuple[22]) {
                $maxCemeteryDelta = [Math]::Max(
                    $maxCemeteryDelta,
                    [Math]::Abs([double]$r3Tuple[22] - [double]$currentFacts.cemetery[0])
                )
            }
            if ($r3Tuple[15] -eq $true -and $null -eq $knownPassSample) {
                $knownPassSample = $currentCellId
            }
            if ($r3Tuple[15] -eq $false -and $null -eq $knownFailSample) {
                $knownFailSample = $currentCellId
            }
        } elseif ($null -eq $noLensSample) {
            $noLensSample = $currentCellId
        }

        $cellTuple = [object[]]@(
            $currentCellId,
            $gridColumn,
            [double]$currentLatitude,
            [double]$currentLongitude,
            $currentMunicipalityIndex,
            $currentFacts.temple,
            $currentFacts.shrine,
            $currentFacts.cemetery,
            $currentFacts.hospital,
            $r3Tuple
        )
        $rowCells.Add($cellTuple)
        $cellCount++
        $previousCompletedGridIndex = $currentGridIndex
    }

    $distanceParser = New-GzipCsvParserFromFile $OrbitDistances
    try {
        $header = $distanceParser.ReadFields()
        Assert-Header $header $ExpectedDistanceHeader "ORBIT distance ledger"
        while (-not $distanceParser.EndOfData) {
            $fields = $distanceParser.ReadFields()
            Assert-True ($fields.Count -eq $ExpectedDistanceHeader.Count) (
                "Malformed ORBIT distance row."
            )
            $cellId = $fields[0]
            if ($null -ne $currentCellId -and $cellId -cne $currentCellId) {
                . $completeCell
                $currentFacts = @{}
            }
            if ($cellId -cne $currentCellId) {
                $currentCellId = $cellId
                $currentGridIndex = [int]$fields[1]
                $currentMunicipalityIndex = Get-NullableInt $fields[3]
                $currentLatitude = Get-NullableDouble $fields[4]
                $currentLongitude = Get-NullableDouble $fields[5]
            } else {
                Assert-True ($currentGridIndex -eq [int]$fields[1]) (
                    "Inconsistent grid index inside cell $cellId."
                )
                Assert-True ($currentLatitude -eq (Get-NullableDouble $fields[4])) (
                    "Inconsistent latitude inside cell $cellId."
                )
                Assert-True ($currentLongitude -eq (Get-NullableDouble $fields[5])) (
                    "Inconsistent longitude inside cell $cellId."
                )
            }
            $category = $fields[6]
            Assert-True ($category -in $ExpectedCategories) (
                "Unexpected ORBIT category '$category'."
            )
            Assert-True (-not $currentFacts.ContainsKey($category)) (
                "Duplicate ORBIT category $category for $cellId."
            )
            $facilityId = $fields[8]
            $summary = $null
            if (-not $facilitySummary.TryGetValue($facilityId, [ref]$summary)) {
                $missingFacilityReferences++
                throw "Nearest facility ID is absent from canonical ledger: $facilityId"
            }
            $name = Get-NullableString $fields[9]
            if ($null -eq $name) { $name = $summary[1] }
            $address = Get-NullableString $fields[10]
            if ($null -eq $address) { $address = $summary[2] }
            $currentFacts[$category] = [object[]]@(
                (Get-NullableDouble $fields[7]),
                $facilityId,
                $name,
                $address,
                (Get-NullableString $fields[11]),
                $summary[3],
                $summary[4],
                $summary[0]
            )
            $distanceCategoryCounts[$category]++
            $distanceRows++
        }
        . $completeCell
        . $flushRow
    } finally {
        $distanceParser.Dispose()
    }

    for ($gridRow = 0; $gridRow -lt 624; $gridRow++) {
        $emptyRowPath = Join-Path $rowsDirectory (
            "g" + $gridRow.ToString("000") + ".json"
        )
        if (-not (Test-Path -LiteralPath $emptyRowPath)) {
            $emptyPayload = [ordered]@{
                schemaVersion = $SchemaVersion
                releaseId = $ReleaseId
                gridRow = $gridRow
                cells = @()
            }
            [IO.File]::WriteAllText(
                $emptyRowPath,
                (Convert-ToCompactJson $emptyPayload 10),
                [Text.UTF8Encoding]::new($false)
            )
            $emptyArtifact = Get-FileArtifact $OutputRoot $emptyRowPath
            $rowArtifacts.Add($emptyArtifact)
            $artifactList.Add($emptyArtifact)
        }
    }
    Assert-True ($rowArtifacts.Count -eq 624) (
        "Every canonical grid row must have a materialized shard."
    )
    $sortedRowArtifacts = @($rowArtifacts | Sort-Object { $_.path })


    Assert-True ($distanceRows -eq $ExpectedDistanceCount) "ORBIT distance row count mismatch."
    Assert-True ($cellCount -eq $ExpectedCellCount) "ORBIT valid cell count mismatch."
    Assert-True ($r3AttachedCount -eq $ExpectedLensCount) (
        "Not every R3 lens cell was attached to an ORBIT cell."
    )
    Assert-True ($missingFacilityReferences -eq 0) "Missing facility references remain."
    foreach ($category in $ExpectedCategories) {
        Assert-True ($distanceCategoryCounts[$category] -eq $ExpectedCellCount) (
            "ORBIT category coverage mismatch for $category."
        )
    }
    Assert-True ($maxR3CoordinateDelta -lt 0.0000001) (
        "R3 and ORBIT canonical coordinates disagree."
    )
    Assert-True ($null -ne $noLensSample) "No no-lens sample was found."
    Assert-True ($null -ne $knownPassSample) "No R3 pass sample was found."
    Assert-True ($null -ne $knownFailSample) "No R3 fail sample was found."

    $manifest = [ordered]@{
        schemaVersion = $SchemaVersion
        releaseId = $ReleaseId
        generatedAt = [DateTimeOffset]::UtcNow.ToString("o")
        formalState = $r3Manifest.formal_state
        sources = @(
            [ordered]@{
                project = "ALL_PROJECT_INTEGRATED_TOP20"
                version = "R3_20260822"
                sha256 = Get-Sha256File $R3Bundle
                innerArtifacts = @(
                    [ordered]@{
                        name = "ALL_LENS_CELL_LEDGER_84060.csv.gz"
                        sha256 = $allLensManifestArtifact.sha256
                    },
                    [ordered]@{
                        name = "SPIRITUAL_PASS_CELL_LEDGER.csv.gz"
                        sha256 = $passManifestArtifact.sha256
                    }
                )
            },
            [ordered]@{
                project = "PROJECT_ORBIT"
                version = "v2_20260822"
                sha256 = $expectedDistanceHash
            },
            [ordered]@{
                project = "PROJECT_ORBIT_FACILITIES"
                version = "v2_20260822"
                sha256 = $expectedFacilityHash
            }
        )
        coverage = [ordered]@{
            totalCells = $ExpectedCellCount
            validCells = $cellCount
            integratedCells = $cellCount
            r3LensCells = $r3AttachedCount
            r3PassLensCells = $r3PassFlagCount
            r3NoLensCells = $cellCount - $r3AttachedCount
            orbitDistanceRows = $distanceRows
            orbitCategoriesPerCell = 4
            canonicalFacilities = $facilitySet.Count
            largeInpatientHospitals = $largeHospitalCount
            missingDistances = 0
            missingFacilityReferences = $missingFacilityReferences
            cemetery = $orbitVerificationData.coverage.cemetery
            hospital = $orbitVerificationData.coverage.hospital
            shrine = $orbitVerificationData.coverage.shrine
            temple = $orbitVerificationData.coverage.temple
        }
        policy = [ordered]@{
            unknownIsSafe = $false
            shrine = "context_only"
            generalHospital = "excluded_from_ranking"
            thresholdsM = [ordered]@{
                temple = 500
                cemetery = 500
                largeInpatientHospital = 500
                strongHistoryEffective = 500
                p8LocatedContext = 500
            }
        }
        qa = [ordered]@{
            status = "PASS"
            r3DuplicateCells = 0
            orbitDuplicateFacilities = 0
            orbitMissingDistances = 0
            publicR3SourcePointersRedacted = $true
            publicR3SourcePointerValuesRedacted = $r3SourcePointerValuesRedacted
            allGridRowsMaterialized = $true
            maxR3OrbitCoordinateDeltaDegrees = $maxR3CoordinateDelta
            maxR3OrbitTempleDistanceDeltaM = $maxTempleDelta
            maxR3OrbitCemeteryDistanceDeltaM = $maxCemeteryDelta
            samples = [ordered]@{
                noLensUnknown = $noLensSample
                r3PassCurrentEvidence = $knownPassSample
                r3Fail = $knownFailSample
            }
        }
        outputs = [ordered]@{
            schema = "schema.json"
            rowShardCount = $sortedRowArtifacts.Count
            facilityShardCount = $facilityArtifactList.Count
            rowShards = $sortedRowArtifacts
            facilityShards = $facilityArtifactList.ToArray()
        }
    }
    $manifestPath = Join-Path $OutputRoot "release-manifest.json"
    [IO.File]::WriteAllText(
        $manifestPath,
        (Convert-ToCompactJson $manifest 80),
        [Text.UTF8Encoding]::new($false)
    )

    $summary = [ordered]@{
        releaseId = $ReleaseId
        outputRoot = [IO.Path]::GetFullPath($OutputRoot)
        manifest = [IO.Path]::GetFullPath($manifestPath)
        rowShards = $sortedRowArtifacts.Count
        facilityShards = $facilityArtifactList.Count
        validCells = $cellCount
        r3LensCells = $r3AttachedCount
        r3PassLensCells = $r3PassFlagCount
        orbitDistanceRows = $distanceRows
        facilities = $facilitySet.Count
        maxR3OrbitCoordinateDeltaDegrees = $maxR3CoordinateDelta
        maxR3OrbitTempleDistanceDeltaM = $maxTempleDelta
        maxR3OrbitCemeteryDistanceDeltaM = $maxCemeteryDelta
        samples = $manifest.qa.samples
    }
    Convert-ToCompactJson $summary 20
} finally {
    if (Test-Path -LiteralPath $workDirectory) {
        $tempRootFull = [IO.Path]::GetFullPath(
            [IO.Path]::GetTempPath()
        ).TrimEnd([IO.Path]::DirectorySeparatorChar) +
            [IO.Path]::DirectorySeparatorChar
        $workDirectoryFull = [IO.Path]::GetFullPath($workDirectory)
        $workDirectoryLeaf = [IO.Path]::GetFileName($workDirectoryFull)
        $insideTempRoot = $workDirectoryFull.StartsWith(
            $tempRootFull,
            [StringComparison]::OrdinalIgnoreCase
        )
        $hasTaskPrefix = $workDirectoryLeaf.StartsWith(
            "iyashiro-integrated-",
            [StringComparison]::Ordinal
        )
        Assert-True ($insideTempRoot -and $hasTaskPrefix) (
            "Refusing unsafe temporary directory cleanup: $workDirectoryFull"
        )
        [IO.Directory]::Delete($workDirectoryFull, $true)
    }
}
