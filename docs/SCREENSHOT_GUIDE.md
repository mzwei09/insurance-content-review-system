# 界面截图指引

本文档说明如何为项目生成界面截图，用于 README 或演示文档。

## 截图目录

截图建议保存至 `docs/screenshots/` 目录，命名规范如下：

| 文件名 | 对应页面 | 说明 |
|--------|----------|------|
| 01-login.png | 登录页面 | 用户名、密码输入框 |
| 02-register.png | 注册页面 | 注册表单 |
| 03-review-empty.png | 审核页面（空） | 文本输入框、图片上传区、示例按钮 |
| 04-review-text.png | 文本审核结果 | 违规/合规判定、违规类型、引用条文 |
| 05-review-images.png | 图片审核结果 | 多图逐张审核结果展示 |
| 06-profile.png | 个人中心 | API 密钥配置、验证、保存 |

## 生成步骤

1. **启动服务**：`bash start.sh`
2. **访问**：http://localhost:8000
3. **按顺序操作**：
   - 登录/注册后进入审核页面
   - 依次访问各页面并截屏
4. **保存**：将截图保存为 PNG 格式至 `docs/screenshots/`

## 截图建议

- 分辨率：建议 1280×800 或以上
- 格式：PNG（便于文档展示）
- 内容：突出核心功能区域，可适当裁剪无关部分

## 目录结构

```
docs/
├── screenshots/          # 截图目录（需手动创建）
│   ├── 01-login.png
│   ├── 02-register.png
│   ├── 03-review-empty.png
│   ├── 04-review-text.png
│   ├── 05-review-images.png
│   └── 06-profile.png
├── SCREENSHOT_GUIDE.md   # 本文件
├── architecture.md
└── PERFORMANCE_ANALYSIS.md
```

创建目录：`mkdir -p docs/screenshots`
