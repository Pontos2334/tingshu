# 听书

一个面向桌面端的全栈听书工作台：把 `AI 创作 -> 文本编辑 -> 语音合成 -> 任务跟踪 -> 入库播放` 收成一条连续流程。后端基于 FastAPI + SQLite，前端基于 Vue 3 + Vite + Element Plus。

## 当前版本重点

这次重构的目标不是继续堆页面，而是把主流程拉直：

- **工作台合并主流程**：AI 创作、直接输入、历史生成稿、试听、合成配置、长任务恢复都在同一页完成
- **音频库按分组展示**：长文本结果按 `group_id / task_id / record_id` 聚合，不再把几十段内容平铺成几十行
- **统一播放器状态**：音色试听、单条播放、长文本队列播放都走同一个底部播放器
- **播放列表契约修正**：播放列表轨道现在返回 `track_id + audio`，删除曲目不再误删失败
- **长任务恢复更稳**：前端持久化 `currentTaskId + taskSnapshot`，刷新页面后可以恢复任务状态
- **打包体积明显下降**：Element Plus 改成按需引入，前端主包从 1MB+ 降到约 397kB

## 界面结构

现在前端只保留 4 个一级入口：

- `工作台`：创作、编辑、试听、合成、任务跟踪
- `音频库`：分组浏览、详情查看、整组播放、加入播放列表
- `音色`：预置音色、自定义音色设计、音色克隆
- `设置`：管理令牌、默认音色、MiMo / DeepSeek Key

## 功能特性

- **AI 创作**：支持模板、风格参考、思考模式、历史生成稿回填
- **语音合成**：支持预置音色、自定义设计音色、克隆音色、风格标签
- **长文本任务**：自动分段、后台异步处理、SSE 进度推送、失败恢复、失败段重试
- **音频库**：按作品聚合浏览、分段详情、收藏、单段下载、整组删除
- **播放列表**：从音频库整组或单段加入，列表内播放与移除
- **全局播放器**：统一支持试听、单条播放、队列播放、拖拽进度、倍速、音量

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3, FastAPI, SQLAlchemy (async), SQLite |
| 前端 | Vue 3, Vite, Pinia, Vue Router, Element Plus, Axios |
| 测试 | pytest, pytest-asyncio, Vitest, jsdom |
| TTS API | 小米 MiMo TTS (`mimo-v2.5-tts`) |
| AI API | DeepSeek (`deepseek-chat` / `deepseek-reasoner` / `deepseek-v4-pro`) |

## 项目结构

```text
tingshu/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── db_models.py
│   │   ├── models.py
│   │   ├── routers/
│   │   │   ├── ai_generate.py
│   │   │   ├── audio.py
│   │   │   ├── playlists.py
│   │   │   ├── settings.py
│   │   │   ├── tts.py
│   │   │   ├── tts_tasks.py
│   │   │   └── voices.py
│   │   └── services/
│   │       ├── ai_service.py
│   │       ├── audio_storage.py
│   │       ├── mimo_tts.py
│   │       ├── synthesis_service.py
│   │       └── text_service.py
│   ├── tests/
│   │   └── test_audio_groups.py
│   ├── requirements.txt
│   └── pytest.ini
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   ├── components/
│   │   ├── stores/
│   │   │   ├── player.js
│   │   │   ├── settings.js
│   │   │   └── workflow.js
│   │   ├── views/
│   │   │   ├── LibraryView.vue
│   │   │   ├── Settings.vue
│   │   │   ├── VoiceManage.vue
│   │   │   └── WorkbenchView.vue
│   │   ├── App.vue
│   │   ├── main.js
│   │   └── router.js
│   └── package.json
├── .gitignore
└── README.md
```

## 快速开始

### 1. 后端

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

编辑 `backend/.env`：

```env
MIMO_API_KEY=你的MiMo_API_Key
DEEPSEEK_API_KEY=你的DeepSeek_API_Key
ADMIN_TOKEN=可选管理密码
```

### 2. 前端

```bash
cd frontend
npm install
npm run dev
```

默认访问 `http://localhost:5173`。如果端口被占用，Vite 会自动切到下一个可用端口。

### 3. 测试

后端：

```bash
cd backend
./venv/bin/pytest tests
```

前端：

```bash
cd frontend
npm test
```

### 4. 生产构建

```bash
cd frontend
npm run build
```

输出目录是 `frontend/dist/`。

## 配置项

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `MIMO_API_KEY` | `""` | MiMo TTS API Key |
| `MIMO_BASE_URL` | `https://api.xiaomimimo.com/v1` | MiMo API 地址 |
| `DEEPSEEK_API_KEY` | `""` | DeepSeek API Key |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com/v1` | DeepSeek API 地址 |
| `ADMIN_TOKEN` | `""` | 管理写操作的 Token，留空则不鉴权 |
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/tingshu.db` | 数据库地址 |
| `AUDIO_STORAGE_PATH` | `./data/audio` | 音频文件根目录 |
| `SAMPLE_STORAGE_PATH` | `./data/samples` | 音色样本根目录 |

## 主要 API

所有 API 前缀都是 `/api`。当 `ADMIN_TOKEN` 已配置时，写操作需要带 `X-Admin-Token`。

### TTS / 任务

- `POST /api/tts/synthesize`
- `POST /api/tts/preview`
- `POST /api/tts/create-task`
- `GET /api/tts/tasks`
- `GET /api/tts/tasks/{task_id}`
- `GET /api/tts/tasks/{task_id}/events`
- `POST /api/tts/tasks/{task_id}/resume`
- `POST /api/tts/tasks/{task_id}/retry-failed`
- `POST /api/tts/tasks/{task_id}/cancel`
- `DELETE /api/tts/tasks/{task_id}`

### AI / 模板

- `POST /api/ai/generate`
- `GET /api/ai/history`
- `DELETE /api/ai/history/{generation_id}`
- `GET /api/ai/templates`
- `POST /api/ai/templates`
- `PUT /api/ai/templates/{template_id}`
- `DELETE /api/ai/templates/{template_id}`

### 音频库

- `GET /api/audio/records`
- `GET /api/audio/records/{record_id}`
- `PUT /api/audio/records/{record_id}/favorite`
- `GET /api/audio/groups`
- `GET /api/audio/groups/{group_id}`
- `DELETE /api/audio/groups/{group_id}`
- `GET /api/audio/file/{record_id}`

### 播放列表

- `GET /api/playlists`
- `POST /api/playlists`
- `DELETE /api/playlists/{playlist_id}`
- `POST /api/playlists/{playlist_id}/tracks`
- `GET /api/playlists/{playlist_id}/tracks`
  - 返回结构：`[{ track_id, sort_order, audio }]`
- `DELETE /api/playlists/{playlist_id}/tracks/{track_id}`

## 说明

- 历史长文本数据不会回填 `synthesis_tasks`，音频库直接依赖现有 `group_id` 聚合展示
- 运行产生的 `backend/data/`、`venv/`、`node_modules/`、`frontend/dist/` 已默认忽略，不会进入版本库
- 当前实现按桌面端优先，没有专门做移动端适配
