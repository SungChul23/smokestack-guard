// 개발 서버에서만 dev-data/(로컬 전용 화면 데이터)를 /dev-data/ 로 내준다. 운영 빌드에는 들어가지 않는다.
// dev-data/는 scripts/build-dev-data.mjs가 만들고 .gitignore에 있다(실제 사업장명·좌표가 들어 있음).
import fs from "node:fs";
import path from "node:path";

export default function devData() {
  const root = path.resolve(import.meta.dirname, "dev-data");
  return {
    name: "dev-data",
    apply: "serve",
    configureServer(server) {
      server.middlewares.use("/dev-data", (req, res, next) => {
        const name = decodeURIComponent((req.url ?? "").split("?")[0]).replace(/^\/+/, "");
        const file = path.resolve(root, name);
        if (!file.startsWith(root + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) return next();
        res.setHeader("Content-Type", "application/json; charset=utf-8");
        fs.createReadStream(file).pipe(res);
      });
    },
  };
}
