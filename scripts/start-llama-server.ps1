param(
    [string]$LlamaServer = ".\\llama-server.exe",
    [string]$ModelPath = "models\\Meta-Llama-3-8B-Instruct.Q4_K_M.gguf",
    [int]$Context = 8192,
    [int]$GpuLayers = 33,
    [int]$Port = 8080
)

& $LlamaServer -m $ModelPath -c $Context -ngl $GpuLayers --port $Port
