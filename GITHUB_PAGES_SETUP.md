# Enabling GitHub Pages for Transcripts

To make the Claude Code transcripts viewable via GitHub Pages, follow these steps:

## Steps to Enable GitHub Pages

1. **Go to Repository Settings**
   - Navigate to https://github.com/tonyandrewmeyer/beszel-k8s-operator/settings/pages

2. **Configure Source**
   - Under "Build and deployment"
   - Set **Source** to: `GitHub Actions`

3. **Trigger the Workflow**
   - The workflow will automatically run on the next push to `main` that includes changes to `.claude/transcripts/**`
   - Or you can manually trigger it from the Actions tab:
     https://github.com/tonyandrewmeyer/beszel-k8s-operator/actions/workflows/pages.yaml

4. **Verify Deployment**
   - Once the workflow runs successfully, transcripts will be available at:
     https://tonyandrewmeyer.github.io/beszel-k8s-operator/

## What Was Implemented

✅ **GitHub Actions Workflow** (`.github/workflows/pages.yaml`)
   - Automatically deploys transcripts to GitHub Pages
   - Triggers on pushes to `main` that affect transcripts
   - Creates a nice index page with links to all transcripts

✅ **Transcript README** (`.claude/transcripts/README.md`)
   - Explains what the transcripts are
   - Provides link to GitHub Pages site

✅ **Main README Update**
   - Added "Development Transcripts" section under Contributing
   - Links to the GitHub Pages site

## How It Works

When the workflow runs:
1. Checks out the repository
2. Copies all transcript files from `.claude/transcripts/` to the deployment directory
3. Generates a root `index.html` that lists all available transcripts
4. Uploads the files as a GitHub Pages artifact
5. Deploys to GitHub Pages

The transcripts maintain their original structure with `index.html` and paginated `page-*.html` files.

## Future Transcripts

Any new transcripts added to `.claude/transcripts/` will automatically be deployed when the changes are pushed to `main`.
