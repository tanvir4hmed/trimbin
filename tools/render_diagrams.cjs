// Re-render PNGs after: python tools/build_architecture_diagrams.py
// Uses the locked web application's existing Sharp dependency: npm ci in web/.
const fs = require("node:fs/promises");
const path = require("node:path");
const sharp = require("../web/node_modules/sharp");

async function main() {
  const directory = path.resolve(__dirname, "../docs/diagrams");
  for (const file of (await fs.readdir(directory)).filter((name) => name.endsWith(".svg"))) {
    await sharp(path.join(directory, file), { density: 144 })
      .png()
      .toFile(path.join(directory, file.replace(/\.svg$/, ".png")));
    console.log(`Rendered ${file}`);
  }
}
main().catch((error) => { console.error(error); process.exitCode = 1; });
