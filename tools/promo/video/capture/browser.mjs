// Chromium for the capture scripts: the system build driven by playwright-core, on the GPU.
import { chromium } from 'playwright-core';
import { serve } from './serve.mjs';

export const CHROMIUM = process.env.CHROMIUM || '/usr/bin/chromium';

// flag sets, best first; preflight.mjs reports which reach the NVIDIA GPU
export const FLAGS = {
  vulkan: ['--headless=new', '--use-gl=angle', '--use-angle=vulkan', '--enable-features=Vulkan', '--ignore-gpu-blocklist'],
  'angle-gl': ['--headless=new', '--use-gl=angle', '--use-angle=gl', '--ignore-gpu-blocklist'],
  'angle-gl-egl': ['--headless=new', '--use-gl=angle', '--use-angle=gl-egl', '--ignore-gpu-blocklist'],
  default: ['--headless=new', '--ignore-gpu-blocklist', '--enable-gpu'],
  headed: ['--use-gl=angle', '--use-angle=vulkan', '--enable-features=Vulkan', '--ignore-gpu-blocklist', '--ozone-platform=wayland'],
  software: ['--headless=new', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'],
};
const COMMON = ['--disable-background-timer-throttling', '--disable-renderer-backgrounding', '--disable-backgrounding-occluded-windows',
  '--autoplay-policy=no-user-gesture-required', '--force-color-profile=srgb', '--disable-lcd-text', '--font-render-hinting=none',
  '--force-device-scale-factor=1'];

export async function launch(flags = 'vulkan') {
  const args = [...(FLAGS[flags] || flags), ...COMMON];
  const headed = !args.some((a) => a.startsWith('--headless'));
  return chromium.launch({
    executablePath: CHROMIUM, headless: !headed, args, ignoreDefaultArgs: ['--headless', '--hide-scrollbars', '--mute-audio'],
    timeout: 30000,
  });
}

// a server on a free port (sinks for frames), and a page of the film at w x h, ready
export async function open(browser, { w = 1920, h = 1080, server, query = '' } = {}) {
  const page = await browser.newPage({ viewport: { width: Math.min(w, 1920), height: Math.min(h, 1080) } });
  const errors = [];
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', (e) => errors.push(e.message));
  const port = server.address().port;
  await page.goto(`http://127.0.0.1:${port}/?capture=1&w=${w}&h=${h}${query}`);
  try {
    await page.evaluate(() => window.film.ready);
  } catch (e) {
    throw new Error(`film did not start: ${e.message}\n${errors.join('\n')}`);
  }
  return { page, errors };
}

export async function server(sinks = {}) {
  return serve({ port: 0, sinks, quiet: !process.env.FILM_VERBOSE });
}
