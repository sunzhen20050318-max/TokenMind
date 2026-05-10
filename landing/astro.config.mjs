import { defineConfig } from 'astro/config';
import tailwindcss from '@tailwindcss/vite';

// https://astro.build/config
export default defineConfig({
  // Pure static output — every page is prerendered to HTML at build time so
  // the entire site can be served from Aliyun OSS static hosting with no
  // runtime requirements.
  output: 'static',

  // We're a single-language brand site for now. Set the canonical site URL
  // here once the production domain is filed; until then, leave undefined
  // so absolute URLs aren't generated incorrectly.
  // site: 'https://tokenmind.example.com',

  vite: {
    plugins: [tailwindcss()],
  },

  // Compress whitespace in HTML output.
  compressHTML: true,
});
