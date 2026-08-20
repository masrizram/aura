@{
    Run = @{
        Path = @('./tests/engine/')
        PassThru = $true
    }
    Output = @{
        Verbosity = 'Detailed'
    }
    Should = @{
        ErrorAction = 'Continue'
    }
}