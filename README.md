# DiskWala Downloader

A Windows command-line downloader for DiskWala shares **when the official public page exposes an authorized media URL**. The current DiskWala web page exposes file metadata but directs viewers to its app. The sample share does not expose a downloadable URL to this tool as of 2026-10-06. The command currently reports `ACCESS_RESTRICTED` for that link; it does not download its video.

## Features

- Validates `https://www.diskwala.com/app/<24-hex-ID>` URLs.
- Inspects public HTML for media in `<video>`, `<source>`, Open Graph video tags, or JSON-LD.
- Downloads a public direct file with streaming, resume, retries, a `.part` file, and atomic completion.
- Uses `yt-dlp` for public HLS media when a playlist URL is exposed.
- Saves to `E:\TeraBoxDownload\Diskwala` with Windows-safe names; avoids overwriting completed files.
- Prints clear error codes and supports sanitized diagnostic logs.

The tool does not use Telegram, Firebase, Rishi's proxy, cookies, or credentials. It does not forge DiskWala's app integrity header. No code was copied from Rishi's unlicensed repository.

## Requirements and installation

- Windows and Python 3.11+ (tested with Python 3.13.2)
- FFmpeg on PATH for HLS remuxing (tested with 9.0.1)
- Internet access

From PowerShell in this repository:

```powershell
py -3.13 -m venv venv
.\venv\Scripts\python.exe -m pip install -e .
```

The only runtime Python dependencies are `requests` and `yt-dlp`. `diskwala.bat` uses the local venv.

## Quick start

Once this project folder is on your user PATH, use:

```powershell
diskwala "https://www.diskwala.com/app/6ac4fca22a52418b24b26ce2"
```

Or invoke the launcher by full path:

```powershell
& 'E:\TeraBoxDownload\Tools\DiskwalaDownloader\diskwala.bat' 'https://www.diskwala.com/app/6ac4fca22a52418b24b26ce2'
```

Output files go to `E:\TeraBoxDownload\Diskwala` automatically. Existing completed files are preserved.

## Inspect without downloading

```powershell
.\venv\Scripts\python.exe -m diskwala_downloader.inspect "https://www.diskwala.com/app/6ac4fca22a52418b24b26ce2"
.\venv\Scripts\python.exe -m diskwala_downloader.inspect "https://www.diskwala.com/app/6ac4fca22a52418b24b26ce2" --verbose
```

The diagnostic prints the share ID, status, and whether a public direct URL was found. On a successfully resolved public media page, it also shows filename, size, type, and stream choice. `--verbose` writes endpoint paths and HTTP status codes to `logs/`, without direct media URLs, cookies, or credentials. Logs are Git-ignored.

## How resolution works

The resolver validates the official share URL, loads its public HTML, and examines standard media elements and metadata. If none is present, it probes the official `/api/v1/file/temp_info` endpoint without private headers or a session to classify the limit. The current server returns `400 Missing Appicrypt header`; the React page itself says to open the file in the DiskWala app. No public media URL is returned. The program stops at `ACCESS_RESTRICTED` instead of inventing a URL or using an unofficial paid resolver.

The official Windows beta's packaged web app references a separate `/desktop/np_lelo` endpoint. Its response is processed as encrypted file metadata and media URL inside the app. The desktop web route returns 404 in an ordinary browser. We inspected the package statically and did not run its unsigned installer or copy its code. Reproducing the app's integrity/decryption mechanism is outside this tool's public-share scope.

If DiskWala later exposes public media in the web page, direct URLs go to the resumable HTTP downloader and `.m3u8` URLs go to `yt-dlp`/FFmpeg. The public metadata response parser also recognizes `fileInfo.name`, `fileInfo.size`, `fileInfo.type`, and `fileInfo.url`, but that response is not currently accessible to a plain HTTP client.

Rishi's reference bot uses an external, unavailable proxy contract: `POST <DISKWALA_PROXY_URL>` with JSON `{"url":"share URL"}` and `x-api-key`. Its response uses `fileInfo.url`, `fileInfo.name`, and `fileInfo.size`. This project does not call that proxy or contain its source.

## Errors and troubleshooting

| Code | Meaning |
|---|---|
| `INVALID_URL` | URL is not a recognized DiskWala `/app/<ID>` share. |
| `ACCESS_RESTRICTED` | The official public page does not expose media, or the API/media URL requires authorization. This is the current sample result. |
| `SHARE_EXPIRED` | Share or media returned HTTP 404; deletion is also possible. |
| `FILE_DELETED` | Server explicitly returned HTTP 410. |
| `DISKWALA_SERVER_ERROR` | DiskWala returned a 5xx response. |
| `RESOLVER_CHANGED` | Unexpected response or changed schema. Run `--verbose` and inspect the endpoint/status log. |
| `NETWORK_ERROR` | Site or API could not be reached. |
| `DOWNLOAD_FAILED` | Media download exhausted retries or failed validation. The `.part` file may be resumed. |

The sample link being reachable does not mean its media is web downloadable. A single failed share is not proof that all shares are unavailable. This tool currently supports only public media exposed by the official web page; it has not been verified to download a real DiskWala file.

## Development and tests

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tests cover URL parsing, HTML/media selection, response parsing, error classes, filenames, output paths, resume, retry, and direct versus HLS selection. Mocked media URLs are used, so tests do not imply live DiskWala download success. The download pipeline can also be tested against a local HTTP media server.

## Legal and usage note

Use only with media you own or have permission to download. The tool does not bypass login, passwords, paywalls, DRM, CAPTCHA, or app access controls. DiskWala's official app and site remain the supported path for app-only shares. Rishi's repository was used for behavioral research only; this code is independently written and licensed under MIT.
