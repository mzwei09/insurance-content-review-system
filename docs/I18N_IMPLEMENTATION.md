# 中英双语支持实现文档

## 概述

本项目已完整实现中英双语支持，包括前端界面、后端 API 响应和文档。用户可以通过点击右上角的语言切换按钮在中文和英文之间切换。

## 实现细节

### 1. 前端国际化 (i18n)

#### 核心机制

在 `frontend/index.html` 中实现了完整的 i18n 系统：

```javascript
// 双语文本映射
const i18nTexts = {
  zh: { /* 中文文本 */ },
  en: { /* 英文文本 */ }
};

// 获取文本函数
function t(key, params = {}) {
  let text = i18nTexts[currentLang][key] || i18nTexts['zh'][key] || key;
  // 支持参数替换，如 {current}, {total}, {seconds}
  Object.keys(params).forEach(k => {
    text = text.replace(new RegExp(`\\{${k}\\}`, 'g'), params[k]);
  });
  return text;
}

// 更新所有 i18n 元素
function updateI18n() {
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.getAttribute('data-i18n');
    const text = t(key);
    // 根据元素类型更新文本或 placeholder
    if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {
      el.placeholder = text;
    } else {
      el.textContent = text;
    }
  });
}

// 切换语言
function switchLanguage(lang) {
  currentLang = lang;
  localStorage.setItem('app_language', lang);
  updateI18n();
}
```

#### 语言切换 UI

在导航栏添加了语言切换按钮：

```html
<div class="lang-switcher">
  <button class="lang-btn active" data-lang-btn="zh" onclick="switchLanguage('zh')">中文</button>
  <button class="lang-btn" data-lang-btn="en" onclick="switchLanguage('en')">EN</button>
</div>
```

#### 翻译覆盖范围

所有用户可见的文本都已添加 `data-i18n` 属性，包括：

- **登录页面**: 标题、表单标签、按钮、提示文本
- **注册页面**: 标题、表单标签、按钮、提示文本
- **审核页面**: 
  - 主标题、副标题
  - 输入框 placeholder
  - 图片上传提示
  - 审核按钮和加载状态
  - 结果显示（合规/违规、违规类型、置信度等）
  - 审核历史
  - 使用说明
- **个人中心**: 
  - 标题、副标题
  - 账号信息
  - API 密钥配置相关文本
- **Toast 提示**: 登录成功、注册成功、API 密钥保存等
- **进度提示**: 审核进度、预计时间等动态文本

#### 语言持久化

用户的语言偏好保存在浏览器的 `localStorage` 中：

```javascript
const DEFAULT_LANG = localStorage.getItem('app_language') || 'zh';
```

刷新页面后，系统会自动恢复用户之前选择的语言。

### 2. 后端国际化

#### 双语消息映射

在 `src/api/main.py` 中定义了双语消息：

```python
I18N_MESSAGES = {
    "zh": {
        "password_too_short": f"密码长度不能少于 {MIN_PASSWORD_LENGTH} 个字符",
        "username_exists": "用户名已存在",
        "user_not_found": "用户不存在",
        "wrong_password": "密码错误",
        "api_key_invalid": "API 密钥无效或已过期，请前往个人中心重新配置",
        # ... 更多消息
    },
    "en": {
        "password_too_short": f"Password must be at least {MIN_PASSWORD_LENGTH} characters",
        "username_exists": "Username already exists",
        "user_not_found": "User not found",
        "wrong_password": "Incorrect password",
        "api_key_invalid": "API key is invalid or expired, please reconfigure in Profile",
        # ... 更多消息
    }
}
```

#### 语言检测

从请求头中获取用户的语言偏好：

```python
def get_lang_from_request(request: Request) -> str:
    """从请求头获取语言偏好"""
    accept_lang = request.headers.get("Accept-Language", "zh")
    if "en" in accept_lang.lower():
        return "en"
    return "zh"
```

#### API 端点更新

关键端点已更新以支持双语响应：

- `/api/auth/register`: 注册错误消息
- `/api/auth/login`: 登录错误消息
- `/api/review`: 审核错误消息
- `/api/review-multimodal`: 多模态审核错误消息
- `/api/user/api-key`: API 密钥相关消息

### 3. 文档国际化

#### README 文档

- **中文文档**: `README.md`
- **英文文档**: `README_EN.md`

两个文档内容完全对应，包括：
- 项目介绍
- 核心功能
- 快速开始
- 系统架构
- API 文档
- 测试指南
- 常见问题

在 `README.md` 顶部添加了语言切换链接：

```markdown
**中文** | [English](README_EN.md)
```

## 使用指南

### 用户端

1. 访问 http://localhost:8000
2. 点击右上角的「中文 / EN」按钮
3. 选择您偏好的语言
4. 语言偏好会自动保存，下次访问时自动应用

### 开发者端

#### 添加新的翻译文本

1. 在 `frontend/index.html` 的 `i18nTexts` 对象中添加新的键值对：

```javascript
const i18nTexts = {
  zh: {
    // ... 现有文本
    new_key: '新的中文文本'
  },
  en: {
    // ... 现有文本
    new_key: 'New English text'
  }
};
```

2. 在 HTML 元素中添加 `data-i18n` 属性：

```html
<p data-i18n="new_key">新的中文文本</p>
```

3. 或在 JavaScript 中使用 `t()` 函数：

```javascript
const text = t('new_key');
```

#### 添加后端错误消息翻译

1. 在 `src/api/main.py` 的 `I18N_MESSAGES` 中添加：

```python
I18N_MESSAGES = {
    "zh": {
        "new_error": "新的错误消息"
    },
    "en": {
        "new_error": "New error message"
    }
}
```

2. 在端点中使用：

```python
@app.post("/api/some-endpoint")
async def some_endpoint(request: Request):
    lang = get_lang_from_request(request)
    raise HTTPException(
        status_code=400, 
        detail=get_message("new_error", lang)
    )
```

## 测试

### 手动测试

1. 启动服务：`bash start.sh`
2. 访问 http://localhost:8000
3. 按照 `test_i18n.html` 中的测试步骤进行验证

### 自动化测试

可以扩展 `tests/test_integration.py` 添加 i18n 相关测试：

```python
def test_api_error_messages_i18n():
    # 测试中文错误消息
    response = client.post(
        "/api/auth/login",
        json={"username": "nonexistent", "password": "test"},
        headers={"Accept-Language": "zh-CN"}
    )
    assert "用户不存在" in response.json()["detail"]
    
    # 测试英文错误消息
    response = client.post(
        "/api/auth/login",
        json={"username": "nonexistent", "password": "test"},
        headers={"Accept-Language": "en-US"}
    )
    assert "User not found" in response.json()["detail"]
```

## 技术决策

### 为什么不使用第三方 i18n 库？

1. **简单性**: 项目是纯 HTML + JavaScript，无需构建工具
2. **轻量级**: 自实现的 i18n 系统只有约 200 行代码
3. **灵活性**: 完全控制翻译逻辑和参数替换
4. **无依赖**: 不引入额外的 npm 包或 CDN 依赖

### 为什么后端只支持简单的语言检测？

1. **实用性**: 对于本项目，简单的 `Accept-Language` 检测已足够
2. **前端主导**: 大部分用户交互在前端完成，后端主要处理错误消息
3. **可扩展**: 如需更复杂的语言协商，可以引入 `python-i18n` 等库

## 未来改进

1. **更多语言**: 可以扩展支持日语、韩语等
2. **动态加载**: 将翻译文本分离到独立的 JSON 文件
3. **翻译管理**: 使用专业的翻译管理平台（如 Crowdin）
4. **复数形式**: 支持更复杂的复数规则
5. **日期时间格式化**: 根据语言格式化日期和时间
6. **数字格式化**: 根据语言格式化数字和货币

## 相关文件

- `frontend/index.html`: 前端 i18n 实现
- `src/api/main.py`: 后端 i18n 实现
- `README.md`: 中文文档
- `README_EN.md`: 英文文档
- `test_i18n.html`: 测试指南

## 贡献

如果您发现翻译错误或有改进建议，欢迎提交 Issue 或 Pull Request。

## 许可证

MIT License
