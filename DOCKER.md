# Docker Setup for Counterfactual Image Generator

This project includes Docker support for easy deployment and consistent environments.

**Windows Note:** This Dockerfile uses a Linux container (Ubuntu), which works perfectly on Windows. Docker Desktop on Windows runs Linux containers by default. The containerized environment is Linux, so Windows-specific code paths in the application won't apply inside the container.

## Building the Docker Image

```bash
docker build -t counterfactual-generator .
```

## Running with Docker

### Basic Usage

**Linux/macOS:**
```bash
# Run with default command (shows help)
docker run --rm counterfactual-generator

# Generate 10 scenes with 5 objects each
docker run --rm -v $(pwd)/output:/app/output counterfactual-generator \
  python3 pipeline.py --num_scenes 10 --num_objects 5 --run_name docker_test

# With GPU support (requires nvidia-docker)
docker run --rm --gpus all -v $(pwd)/output:/app/output counterfactual-generator \
  python3 pipeline.py --num_scenes 10 --num_objects 5 --use_gpu 1
```

**Windows (PowerShell):**
```powershell
# Run with default command (shows help)
docker run --rm counterfactual-generator

# Generate 10 scenes with 5 objects each
docker run --rm -v ${PWD}/output:/app/output counterfactual-generator `
  python3 pipeline.py --num_scenes 10 --num_objects 5 --run_name docker_test

# With GPU support (requires WSL2 and nvidia-docker)
docker run --rm --gpus all -v ${PWD}/output:/app/output counterfactual-generator `
  python3 pipeline.py --num_scenes 10 --num_objects 5 --use_gpu 1
```

**Windows (Command Prompt):**
```cmd
docker run --rm -v "%CD%/output:/app/output" counterfactual-generator ^
  python3 pipeline.py --num_scenes 10 --num_objects 5 --run_name docker_test
```

### Using Docker Compose

```bash
# Build and run with docker-compose
docker-compose up

# Run in detached mode
docker-compose up -d

# View logs
docker-compose logs -f

# Stop the container
docker-compose down
```

### Customize the Command

Edit `docker-compose.yml` to change the default command:

```yaml
command: python3 pipeline.py --num_scenes 10 --num_objects 5 --use_gpu 1 --run_name my_experiment
```

## Volume Mounting

The output directory is mounted to `./output` on your host machine, so generated scenes and images will persist after the container stops.

## GPU Support

For GPU rendering support, ensure you have:
1. NVIDIA Docker runtime installed
2. Use `--gpus all` flag with `docker run` or add to `docker-compose.yml`:

```yaml
deploy:
  resources:
    reservations:
      devices:
        - driver: nvidia
          count: all
          capabilities: [gpu]
```

## Windows-Specific Notes

1. **Docker Desktop Required**: Install Docker Desktop for Windows from [docker.com](https://www.docker.com/products/docker-desktop)

2. **Path Format**: Use forward slashes or PowerShell variables:
   - PowerShell: `-v ${PWD}/output:/app/output`
   - CMD: `-v "%CD%/output:/app/output"`
   - Or use absolute paths: `-v C:/path/to/output:/app/output`

3. **WSL2**: Docker Desktop on Windows uses WSL2. Make sure WSL2 is enabled in Windows features.

4. **GPU Support on Windows**: Requires:
   - WSL2 with NVIDIA GPU driver
   - nvidia-docker installed in WSL2
   - May not work on all Windows setups

## Troubleshooting

### Blender Not Found
If you get errors about Blender not being found, verify the installation:
```bash
# Linux/macOS
docker run --rm counterfactual-generator blender --version

# Windows PowerShell
docker run --rm counterfactual-generator blender --version
```

### Permission Issues
**Linux/macOS:**
```bash
sudo chown -R $USER:$USER output/
```

**Windows:** Usually not an issue, but if you encounter permission errors, run Docker Desktop as Administrator or adjust folder permissions.

### Interactive Shell
**Linux/macOS:**
```bash
docker run --rm -it -v $(pwd)/output:/app/output counterfactual-generator /bin/bash
```

**Windows (PowerShell):**
```powershell
docker run --rm -it -v ${PWD}/output:/app/output counterfactual-generator /bin/bash
```

## Notes

- The image includes Blender 4.3, which is compatible with the codebase
- Credentials and tokens are excluded from the Docker image for security
- Output files are stored in the mounted volume to persist data