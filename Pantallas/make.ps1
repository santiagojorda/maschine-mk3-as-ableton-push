param(
    [Parameter(Position=0)]
    [string]$Target = "help"
)

& "$PSScriptRoot\make.bat" $Target @args
