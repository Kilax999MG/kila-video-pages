# Kila Shorts

Mobile YouTube-to-Shorts workflow. GitHub Pages is the frontend; GitHub Actions runs the pinned, open-source [Chopify](https://github.com/mehbul/chopify) pipeline and publishes finished clips as public GitHub Releases.

## First Short

1. Open [Kila Shorts](https://kilax999mg.github.io/kila-video-pages/) on Android Chrome.
2. Paste a YouTube video URL, choose the clip settings, and tap **Create Shorts**.
3. On GitHub, review the pre-filled Issue and tap **Submit new issue**.
4. Wait for the Actions run to finish. The Issue receives a comment with the Release link and closes on success.
5. Return to the page and download the MP4 under **Finished Shorts** (or open Releases).

Only submit videos you own or have permission to reuse. Private, protected, or authentication-required videos are not supported. YouTube may temporarily block GitHub-hosted runners; failed downloads remain failed and are reported in the workflow and Issue.

### YouTube bot-check handling

The workflow installs current `yt-dlp[default]`, Deno/EJS, and the BgUtils PO-token provider (`bgutil-ytdlp-pot-provider` 2.0.0). A local provider container supplies PO tokens to the recommended `mweb` YouTube client, and a preflight verifies that the selected video can actually be resolved before Whisper/rendering starts. This materially improves GitHub-runner reliability, but YouTube can still reject a datacenter IP/session.

As an optional fallback, an owner can add their own exported Netscape-format cookie file as the repository Actions secret `YOUTUBE_COOKIES`. The workflow writes it only to a temporary runner file and removes it after the job. Never use cookies from public dumps or another person: cookies can grant access to the associated Google account. Cookies are not required for normal public videos and do not guarantee that YouTube will accept a GitHub-hosted runner.

## Channel Auto Mode

1. Select **Channel Auto** on the Pages site, paste a channel videos URL such as `https://youtube.com/@channel/videos`, choose settings, and tap **Enable Channel Auto-Shorts**.
2. Submit the prepared configuration Issue. New uploads are checked every six hours; an upload is recorded in `state/last_video.txt` only after its clips are rendered and released.
3. Turn **Processing enabled** off and submit an updated configuration to pause channel processing.

The scheduled workflow skips disabled or missing configurations and videos already recorded as processed. Automatic processing follows the same ownership and permission requirement as one-off jobs.

## One GitHub Setting

In repository **Settings → Actions → General → Workflow permissions**, allow **Read and write permissions**. The workflow uses GitHub's automatically provided token; no token is placed in the site or needs to be created. Keep Issues enabled so the mobile form can submit jobs.

The site reads public Actions runs and Releases without authentication. Issues from authors who are not repository owners, members, or collaborators are never processed. Rendering uses CPU-only GitHub-hosted runners and may take a while for long videos.

## Verification

Local parser and static checks are run with:

```sh
python -m unittest discover -s tests -v
python -m py_compile scripts/*.py
```

The live GitHub Actions render requires repository permissions and depends on YouTube availability, so a complete external YouTube render was not run as part of local verification.