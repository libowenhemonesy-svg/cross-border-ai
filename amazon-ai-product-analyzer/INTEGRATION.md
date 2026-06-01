# Amazon AI Product Analyzer 与 Amazon Agent 集成说明

## 功能介绍

Chrome 插件现在可以将提取的商品数据直接发送到 Amazon Agent 后端进行分析和存储。

## 集成功能

1. **数据提取**：从 Amazon 商品页面提取商品信息
2. **数据发送**：将提取的数据发送到 Amazon Agent 后端
3. **数据存储**：后端自动将数据存储到数据库
4. **AI 分析**：后续可以通过 Amazon Agent 进行 AI 分析

## 使用步骤

### 1. 启动 Amazon Agent 后端

```bash
cd C:\Users\里\Documents\Amazon Agent
python -m uvicorn app.main:app --host 0.0.0.0 --port 8010 --reload
```

### 2. 安装 Chrome 插件

1. 打开 Chrome 浏览器
2. 访问 `chrome://extensions/`
3. 开启"开发者模式"
4. 点击"加载已解压的扩展程序"
5. 选择 `amazon-ai-product-analyzer` 文件夹

### 3. 使用插件

1. 打开 Amazon 商品详情页
2. 点击浏览器右上角的插件图标
3. 点击"提取当前商品信息"
4. 查看提取的数据
5. 点击"发送到 Amazon Agent 后端"按钮
6. 数据将被发送并存储到后端

### 4. 查看数据

数据发送成功后，可以通过以下方式查看：

1. **直接访问后端 API**：
   ```
   http://localhost:8010/api/chrome/products
   ```

2. **通过 Amazon Agent 前端**：
   访问 http://localhost:8010 查看运营台

## 数据字段说明

| 字段 | 说明 | 示例 |
|------|------|------|
| title | 商品标题 | "Apple iPhone 15 Pro Max" |
| price | 商品价格 | "$1,199.00" |
| rating | 商品评分 | "4.7 out of 5 stars" |
| review_count | 评论数量 | "1,234 ratings" |
| bullets | 五点描述 | ["Feature 1", "Feature 2", ...] |
| url | 商品链接 | "https://www.amazon.com/dp/..." |
| asin | ASIN 编码 | "B0CHX3QBCH" |
| reviews | 差评列表 | [{title, content, rating, date}] |

## API 接口

### 1. 提交商品数据

**请求**：
```
POST http://localhost:8010/api/chrome/submit
Content-Type: application/json

{
  "title": "商品标题",
  "price": "$1,199.00",
  "rating": "4.7 out of 5 stars",
  "review_count": "1,234 ratings",
  "bullets": ["Feature 1", "Feature 2"],
  "url": "https://www.amazon.com/dp/B0CHX3QBCH",
  "asin": "B0CHX3QBCH",
  "reviews": []
}
```

**响应**：
```json
{
  "success": true,
  "message": "数据已保存",
  "asin": "B0CHX3QBCH",
  "price": 1199.0,
  "rating": 4.7,
  "review_count": 1234
}
```

### 2. 获取已提交的商品列表

**请求**：
```
GET http://localhost:8010/api/chrome/products
```

**响应**：
```json
{
  "products": [
    {
      "asin": "B0CHX3QBCH",
      "title": "B0CHX3QBCH",
      "url": "https://www.amazon.com/dp/B0CHX3QBCH",
      "marketplace": "US"
    }
  ]
}
```

## 故障排除

### 1. 发送失败：无法连接到后端

**原因**：Amazon Agent 后端未启动

**解决**：
```bash
cd C:\Users\里\Documents\Amazon Agent
python -m uvicorn app.main:app --host 0.0.0.0 --port 8010 --reload
```

### 2. 发送失败：CORS 错误

**原因**：浏览器跨域限制

**解决**：后端已配置 CORS 允许所有来源，如果仍有问题，尝试刷新页面或重启浏览器。

### 3. 数据未显示

**原因**：数据存储在数据库中，需要通过 API 或前端查看

**解决**：
- 访问 http://localhost:8010/api/chrome/products 查看数据
- 或访问 http://localhost:8010 通过前端查看

## 下一步计划

1. **AI 分析功能**：接入大模型 API，对商品进行智能分析
2. **批量分析**：支持批量提取和分析多个商品
3. **竞品对比**：自动对比同类商品的优劣势
4. **选品推荐**：基于数据分析给出选品建议

## 技术支持

如有问题，请提交 Issue 或联系开发者。