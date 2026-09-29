$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskOriginalPath = $env:PATH
Push-Location -LiteralPath $taskRoot
try {
    if (Test-Path -LiteralPath 'C:\msys64\mingw64\bin\g++.exe') {
        $env:PATH = 'C:\msys64\mingw64\bin;' + $env:PATH
    }
    New-Item -ItemType Directory -Force build | Out-Null
    & g++ -std=c++17 -pthread -Wall -Wextra -Wpedantic -static -Iedge edge/main.cpp edge/simulator/Machine.cpp edge/agent/EdgeAgent.cpp edge/agent/NetworkClient.cpp -o build/fabtwin-edge.exe
    if ($LASTEXITCODE -ne 0) { throw 'C++ build failed. Use a C++17 compiler with std::thread support (MSYS2 MinGW-w64 or MSVC/CMake).' }
} finally { $env:PATH = $taskOriginalPath; Pop-Location }
