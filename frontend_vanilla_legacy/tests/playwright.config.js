module.exports = {
  testDir: '.',
  timeout: 30000,
  use: {
    headless: true,
    // Chromium 128+ ships Ed25519 in SubtleCrypto, which the wallet needs
    channel: undefined,
  },
  reporter: [['list']],
};
