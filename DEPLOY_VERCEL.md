# Deploying to Vercel

## Quick Deploy

1. **Push your code to GitHub** (if not already).

2. **Import to Vercel**
   - Go to [vercel.com](https://vercel.com) and sign in
   - Click **Add New** → **Project**
   - Import your GitHub repository

3. **Configure the project**
   - **Root Directory**: Set to `eye_test_engine` (required)
   - **Framework Preset**: Other (Vercel will auto-detect Flask)
   - **Build Command**: Leave empty
   - **Install Command**: `pip install -r requirements.txt` (or leave default)

4. **Deploy** – Click Deploy. Your app will be live at `https://your-project.vercel.app`.

## Important Notes

### Session state
Vercel uses serverless functions. In-memory sessions may not persist reliably across requests (each request can hit a different instance). For production use with multiple concurrent users, consider adding [Vercel KV](https://vercel.com/docs/storage/vercel-kv) or another external session store.

### Logging
On Vercel, logs are written to `/tmp`, which is ephemeral and cleared between deployments. Session CSVs and metadata will not persist. For persistent logging, integrate with a cloud storage service (e.g. S3, Vercel Blob).

### Local development
Local development is unchanged. Run `./start_frontend.sh` from `eye_test_engine` for the usual frontend + backend setup.
