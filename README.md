# VoiceGuard File Processor

A Python tool for batch processing audio files through the VoiceGuard backend system to detect AI-generated or manipulated voice content.

Set up the environment using after installing the `conda` CLI: 

1. `conda env create -f environment.yml`
2. `conda env create -f voiceguard-processor.yaml`

## Usage

```bash
python __main__.py /path/to/audio/directory \
    --extensions .wav .mp3 .m4a \
    --api-key YOUR_API_KEY \
    --backend-url https://your-backend-url/query \
    --output both
```

### Command Line Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `directory` | Directory containing files to process | Required |
| `--extensions` | Allowed file extensions | `.wav` |
| `--api-key` | API key for authentication | None (reads from `API_KEY` env var) |
| `--backend-url` | Backend GraphQL endpoint | Production VoiceGuard URL |
| `--output` | Output format: `csv`, `json`, or `both` | `csv` |

### Environment Variables

You can set these environment variables instead of using command line arguments:

```bash
export API_KEY="your-api-key-here"
export BACKEND_URL="https://your-backend-url/query"
```

An example value for `BACKEND_URL` is `https://app.api.voiceguard.realitydefender.xyz/query`, which is what you would use if you're trying to use the multi-tenant VoiceGuard production API.

## Output Formats

### CSV Output (`results_YYYYMMDD_HHMMSS.csv`)

Contains basic analysis results:

| Column | Description |
|--------|-------------|
| `original_filename` | Path to the original file |
| `file_id` | Backend system file ID |
| `stream_id` | Backend system stream ID |
| `status` | Processing status |
| `conclusion` | Analysis result (HUMAN, AI, INCONCLUSIVE) |
| `probability` | Confidence score (0.0-1.0) |
| `reason` | Additional details for inconclusive results |

### JSON Output (`results_YYYYMMDD_HHMMSS.json`)

Contains detailed analysis data including:
- Complete stream metadata
- Segment-by-segment analysis
- Model results and preprocessing information
- Timestamps and processing details

## Examples

### Process WAV files with CSV output
```bash
python __main__.py ./audio_samples
```

### Process multiple formats with detailed JSON output
```bash
python __main__.py ./recordings \
    --extensions .wav .mp3 .m4a .flac \
    --output json \
    --api-key abc123
```

### Process with both output formats
```bash
python __main__.py ./test_audio \
    --output both \
    --extensions .wav .mp3
```

## Configuration

### Authentication

For production environments, you must provide an API key:

1. **Command line**: `--api-key YOUR_KEY`
2. **Environment variable**: `export API_KEY="YOUR_KEY"`

Localhost URLs (containing `localhost` or `127.0.0.1`) don't require authentication.

You only need to supply either the `--api-key` flag or set the `API_KEY` environment variable. If both are set, the `--api-key` flag takes precedence.

### Backend URL

Default backend URL points to the production VoiceGuard API. For development or custom deployments:

```bash
python __main__.py ./audio \
    --backend-url http://localhost:8080/query
```

## Error Handling

The tool includes comprehensive error handling:

- **Network errors**: Automatic retries with exponential backoff
- **File processing errors**: Logged and recorded in output files
- **Timeout handling**: Based on audio file duration + buffer time
- **API errors**: Detailed GraphQL error reporting

## Logging

The tool provides informational logging by default:
- Processing progress and status updates
- Error messages and warnings
- Completion summaries

Debug logging is available internally for troubleshooting.

## File Processing Flow

1. **File Discovery**: Recursively scan directory for files with allowed extensions
2. **Upload Process**: 
   - Calculate file metadata (SHA256, MIME type, size)
   - Create file blob in backend
   - Upload file to storage
   - Create processing job
3. **Monitoring**: Poll backend for completion status
4. **Results**: Fetch and save analysis results

## Supported Audio Formats

The tool can process any audio format supported by the backend system. Common formats include:

- WAV (`.wav`)
- MP3 (`.mp3`)
- M4A (`.m4a`)
- FLAC (`.flac`)

Specify formats using the `--extensions` argument.

## Troubleshooting

### Common Issues

**"No files found with allowed extensions"**
- Check file extensions in your directory
- Verify `--extensions` argument matches your files

**"API key must be provided"**
- Set API key via `--api-key` or `API_KEY` environment variable
- Localhost URLs don't require API keys

**"Processing timed out"**
- Large files may need more time
- Check network connectivity
- Verify backend system is responding

**Audio duration detection fails**
- Install ffmpeg for broader format support
- Check file integrity
