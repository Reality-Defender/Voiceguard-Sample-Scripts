# VoiceGuard File Processor

A Python tool for batch processing audio files through the VoiceGuard backend system to detect AI-generated or manipulated voice content.

Set up the environment using after installing the `conda` CLI: 

1. `conda env create -f environment.yml`
2. `conda activate voiceguard-processor`

## Usage

```bash
 python __main__.py <directory>
    --extensions wav mp3 m4a
    --api-key <api_key>
    --output csv json
    --backend-url https://app.api.voiceguard.realitydefender.xyz/query
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
export BACKEND_URL="https://app.api.voiceguard.realitydefender.xyz/query"
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

## Supported Audio Formats

The tool can process any audio format supported by the backend system. Common formats include:

- WAV (`.wav`)
- MP3 (`.mp3`)
- M4A (`.m4a`)
- FLAC (`.flac`)

Specify formats using the `--extensions` argument.

