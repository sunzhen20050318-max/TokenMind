/**
 * Single source of truth for the installer URLs surfaced on the landing page.
 *
 * These mirror what `versions.json` at the repo root publishes to the desktop
 * client's update channel — kept hand-written here (instead of fetched at
 * build time) because (1) the landing build runs before versions.json is
 * known to be the deployable copy, and (2) we sometimes promote a build to
 * the website that hasn't been pushed to versions.json yet (e.g. the macOS
 * package lags Windows).
 *
 * Whenever you bump versions.json, copy the same URLs here.
 */
export interface InstallerLinks {
  macos: string | null;
  windows: string | null;
}

export const INSTALLERS: InstallerLinks = {
  // 0.1.13 macOS DMG — built on Apple Silicon (arm64 only). Intel Macs
  // running this DMG will work via Rosetta 2 for the Python runtime, but
  // a native x64 build is still TODO. Update both here AND in the repo's
  // versions.json when a new DMG is published.
  macos: 'https://tokenmind.oss-cn-shenzhen.aliyuncs.com/TokenMind-0.1.13-arm64.dmg',
  windows:
    'https://tokenmind.oss-cn-shenzhen.aliyuncs.com/TokenMindSetup-0.1.12.exe',
};
