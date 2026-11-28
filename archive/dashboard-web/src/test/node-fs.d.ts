// 시험에서 스타일 파일(CSS) 원문을 읽는 데만 쓴다. @types/node를 프로젝트에 새로 들이지 않으려고 필요한 한 함수만 선언한다.
declare module "node:fs" {
  export function readFileSync(path: string, encoding: "utf8"): string;
}
