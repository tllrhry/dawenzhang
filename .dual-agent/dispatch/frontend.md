# Frontend 域差异

React 19 + Vite 6 + TypeScript 5.7（`frontend/`）。已引入 Ant Design 5（`ConfigProvider` 默认主题）与 `react-router-dom`；构建工具在 `devDependencies`。验证走既有脚本：类型检查/测试 `npm run test`（当前=`tsc --noEmit`，无运行时测试框架），构建 `npm run build`（`tsc -b && vite build`）。严格 TS，不引入 `any` 兜底。

后端地址/前缀走配置或环境变量，不硬编码：现有约定 `apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '')`。dev（vite 5173）下相对 `/api/v1` 不会自动到达后端（8000），如需真实联调须在 `vite.config.ts` 加 `server.proxy` 到 `http://127.0.0.1:8000` 或设 `VITE_API_BASE_URL`——此类构建配置改动需任务明确授权。改动优先限定在 `frontend/src`。
