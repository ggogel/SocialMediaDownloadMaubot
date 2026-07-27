# SocialMediaDownloadMaubot

Share social media content directly in your Matrix room with this [Maubot](https://github.com/maubot/maubot) plugin! Just paste a link, and it will download and post the content for everyone to see.

Currently supported social media platforms:
  - Reddit
  - Instagram (Might not work anymore because Instagram has massively restricted anonymous access.)
  - YouTube
  - TikTok
  - Bluesky

Choose what to download by configuring the plugin.

## Installation

Download the latest `.mbp` from the Releases section and add it as a plugin in
the Maubot Manager. Instaloader is bundled in the plugin package, so it does not
need to be installed in the Maubot environment.

## Building

Build a self-contained plugin package from the repository root:

```shell
./scripts/build-mbp.sh
```

The build installs the version pinned in `requirements.txt` into a temporary
directory and creates `package.mbp` without storing third-party source in the
repository.
