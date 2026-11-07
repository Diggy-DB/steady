import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
// BASE_PATH is where the site lives: "/" locally, "/<repo name>/" on GitHub Pages
// (set by .github/workflows/pages.yml).
export default defineConfig({
  base: process.env.BASE_PATH || '/',
  plugins: [react()],
})
