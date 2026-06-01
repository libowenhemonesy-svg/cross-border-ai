/**
 * Amazon商品信息提取脚本
 * 功能：从Amazon商品详情页提取商品信息
 * 运行环境：Amazon商品详情页
 */

// 标记脚本已加载
window.__amazonAnalyzerLoaded = true;

// 监听来自popup.js的消息
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  console.log('收到消息:', request);

  // 检查是否是获取商品信息的请求
  if (request.action === 'GET_PRODUCT_INFO') {
    try {
      // 提取商品信息
      const productInfo = extractProductInfo();
      console.log('提取到的商品信息:', productInfo);
      // 返回提取结果
      sendResponse({ success: true, data: productInfo });
    } catch (error) {
      // 如果提取失败，返回错误信息
      console.error('提取商品信息失败:', error);
      sendResponse({ success: false, error: error.message });
    }
    return false; // 同步响应，不需要 return true
  }

  // 检查是否是获取评论的请求
  if (request.action === 'GET_REVIEWS') {
    try {
      // 提取评论信息
      const reviews = extractReviews();
      console.log('提取到的评论:', reviews);
      // 返回提取结果
      sendResponse({ success: true, data: reviews });
    } catch (error) {
      // 如果提取失败，返回错误信息
      console.error('提取评论失败:', error);
      sendResponse({ success: false, error: error.message });
    }
    return false; // 同步响应，不需要 return true
  }

  return false;
});

// 脚本加载完成日志
console.log('Amazon AI Product Analyzer content script loaded');

/**
 * 提取商品信息的主函数
 * @returns {Object} 包含商品信息的对象
 */
function extractProductInfo() {
  const productInfo = {
    title: extractTitle(),
    price: extractPrice(),
    rating: extractRating(),
    reviewCount: extractReviewCount(),
    bullets: extractBullets(),
    image: extractImage(),
    url: window.location.href,
    asin: extractASIN()
  };

  return productInfo;
}

/**
 * 提取商品主图
 * @returns {string} 图片URL或空字符串
 */
function extractImage() {
  console.log('开始提取图片...');

  // 方法1：直接查找主图 img
  const mainImg = document.querySelector('#landingImage');
  if (mainImg) {
    console.log('找到 #landingImage');
    if (mainImg.src && mainImg.src.startsWith('http')) {
      return mainImg.src;
    }
    // 检查 data-old-hires
    const hires = mainImg.getAttribute('data-old-hires');
    if (hires) return hires;
  }

  // 方法2：查找图片容器中的 img
  const imgBlock = document.querySelector('#imageBlock');
  if (imgBlock) {
    const imgs = imgBlock.querySelectorAll('img');
    console.log('找到 #imageBlock 中的图片数量:', imgs.length);
    for (const img of imgs) {
      // 跳过小图标和精灵图
      if (img.src && img.src.includes('media-amazon.com') && !img.src.includes('sprite')) {
        return img.src;
      }
      // 检查 data-old-hires
      const hires = img.getAttribute('data-old-hires');
      if (hires) return hires;
    }
  }

  // 方法3：查找所有带 data-old-hires 的图片
  const allHires = document.querySelectorAll('img[data-old-hires]');
  console.log('找到 data-old-hires 图片数量:', allHires.length);
  for (const img of allHires) {
    const hires = img.getAttribute('data-old-hires');
    if (hires && hires.includes('media-amazon.com')) {
      return hires;
    }
  }

  // 方法4：查找所有 Amazon CDN 图片
  const allAmazonImgs = document.querySelectorAll('img[src*="media-amazon.com"]');
  console.log('找到 Amazon CDN 图片数量:', allAmazonImgs.length);
  for (const img of allAmazonImgs) {
    // 跳过太小的图片（可能是图标）
    if (img.naturalWidth > 100 || img.width > 100) {
      return img.src;
    }
  }

  // 方法5：查找主图区域的任何图片
  const wrapper = document.querySelector('#imgTagWrapperId') || document.querySelector('#mainImageContainer');
  if (wrapper) {
    const img = wrapper.querySelector('img');
    if (img && img.src) {
      return img.src;
    }
  }

  console.log('未找到图片');
  return '';
}

/**
 * 提取商品标题
 * @returns {string} 商品标题或"未找到"
 */
function extractTitle() {
  // 优先从#productTitle获取
  const titleElement = document.getElementById('productTitle');
  if (titleElement) {
    return titleElement.textContent.trim();
  }

  // 备用方案：从其他可能的元素获取
  const titleSelectors = [
    '#title',
    '.product-title',
    'h1.a-size-large',
    'h1'
  ];

  for (const selector of titleSelectors) {
    const element = document.querySelector(selector);
    if (element && element.textContent.trim()) {
      return element.textContent.trim();
    }
  }

  return '未找到';
}

/**
 * 提取商品价格
 * @returns {string} 商品价格或"未找到"
 */
function extractPrice() {
  // 优先从.a-price .a-offscreen获取
  const priceElement = document.querySelector('.a-price .a-offscreen');
  if (priceElement) {
    return priceElement.textContent.trim();
  }

  // 备用方案：从其他可能的元素获取
  const priceSelectors = [
    '#priceblock_ourprice',
    '#priceblock_dealprice',
    '.a-price-whole',
    '.a-color-price'
  ];

  for (const selector of priceSelectors) {
    const element = document.querySelector(selector);
    if (element && element.textContent.trim()) {
      return element.textContent.trim();
    }
  }

  return '未找到';
}

/**
 * 提取商品评分
 * @returns {string} 商品评分或"未找到"
 */
function extractRating() {
  // 优先从#acrPopover获取
  const ratingElement = document.getElementById('acrPopover');
  if (ratingElement) {
    const ratingText = ratingElement.getAttribute('title');
    if (ratingText) {
      return ratingText;
    }
  }

  // 备用方案：从.a-icon-alt获取
  const ratingIcon = document.querySelector('.a-icon-alt');
  if (ratingIcon) {
    return ratingIcon.textContent.trim();
  }

  return '未找到';
}

/**
 * 提取评论数
 * @returns {string} 评论数或"未找到"
 */
function extractReviewCount() {
  // 优先从#acrCustomerReviewText获取
  const reviewElement = document.getElementById('acrCustomerReviewText');
  if (reviewElement) {
    return reviewElement.textContent.trim();
  }

  // 备用方案：从其他可能的元素获取
  const reviewSelectors = [
    '#acrCustomerReviewCount',
    '.a-size-base',
    '[data-hook="total-review-count"]'
  ];

  for (const selector of reviewSelectors) {
    const element = document.querySelector(selector);
    if (element && element.textContent.trim()) {
      return element.textContent.trim();
    }
  }

  return '未找到';
}

/**
 * 提取五点描述
 * @returns {Array<string>} 五点描述数组或空数组
 */
function extractBullets() {
  const bullets = [];

  // 从#feature-bullets li获取
  const bulletElements = document.querySelectorAll('#feature-bullets li');

  bulletElements.forEach(element => {
    const text = element.textContent.trim();
    // 过滤空文本和"显示更多"按钮
    if (text && !text.includes('显示更多') && !text.includes('Show more')) {
      bullets.push(text);
    }
  });

  // 如果没有找到，尝试其他选择器
  if (bullets.length === 0) {
    const alternativeSelectors = [
      '.a-unordered-list .a-list-item',
      '.feature-list li',
      '.product-feature li'
    ];

    for (const selector of alternativeSelectors) {
      const elements = document.querySelectorAll(selector);
      if (elements.length > 0) {
        elements.forEach(element => {
          const text = element.textContent.trim();
          if (text) {
            bullets.push(text);
          }
        });
        break;
      }
    }
  }

  return bullets;
}

/**
 * 提取ASIN
 * @returns {string} ASIN或"未找到"
 */
function extractASIN() {
  // 方法1：从URL中提取
  const url = window.location.href;
  const asinMatch = url.match(/\/dp\/([A-Z0-9]{10})/);
  if (asinMatch) {
    return asinMatch[1];
  }

  // 方法2：从页面元素中提取
  const asinSelectors = [
    '#ASIN',
    '[name="ASIN"]',
    '[data-asin]'
  ];

  for (const selector of asinSelectors) {
    const element = document.querySelector(selector);
    if (element) {
      const asin = element.value || element.getAttribute('data-asin');
      if (asin) {
        return asin;
      }
    }
  }

  return '未找到';
}

/**
 * 提取差评信息（1-2星）
 * @returns {Array} 差评数组
 */
function extractReviews() {
  const reviews = [];

  // 尝试多种评论选择器
  const reviewSelectors = [
    '[data-hook="review"]',
    '.review',
    '.a-section.review',
    '[id^="customer_review"]',
    '.a-section.celwidget'
  ];

  let reviewElements = [];

  // 尝试不同的选择器
  for (const selector of reviewSelectors) {
    reviewElements = document.querySelectorAll(selector);
    if (reviewElements.length > 0) {
      console.log(`找到评论，使用选择器: ${selector}, 数量: ${reviewElements.length}`);
      break;
    }
  }

  // 如果没有找到评论，尝试滚动到评论区域
  if (reviewElements.length === 0) {
    console.log('未找到评论，尝试查找评论区域...');

    // 尝试找到评论区域
    const reviewSection = document.getElementById('reviews-medley-footer') ||
                         document.querySelector('[data-hook="reviews-medley-footer"]') ||
                         document.getElementById('reviewsMedley');

    if (reviewSection) {
      console.log('找到评论区域，尝试提取...');

      // 在评论区域内查找评论
      for (const selector of reviewSelectors) {
        reviewElements = reviewSection.querySelectorAll(selector);
        if (reviewElements.length > 0) {
          console.log(`在评论区域内找到评论，使用选择器: ${selector}`);
          break;
        }
      }
    }
  }

  // 如果还是没有找到，尝试更通用的方法
  if (reviewElements.length === 0) {
    console.log('尝试通用方法查找评论...');

    // 查找所有包含评分的元素
    const ratingElements = document.querySelectorAll('[data-hook="review-star-rating"], .review-rating, .a-icon-alt');

    if (ratingElements.length > 0) {
      console.log(`找到 ${ratingElements.length} 个评分元素`);

      // 从评分元素向上查找评论容器
      ratingElements.forEach((ratingEl, index) => {
        if (index >= 20) return;

        // 向上查找评论容器
        let reviewContainer = ratingEl.closest('[data-hook="review"]') ||
                             ratingEl.closest('.review') ||
                             ratingEl.closest('.a-section');

        if (reviewContainer && !reviews.some(r => r.element === reviewContainer)) {
          const reviewData = extractReviewFromElement(reviewContainer);
          if (reviewData) {
            reviewData.element = reviewContainer;
            reviews.push(reviewData);
          }
        }
      });
    }
  } else {
    // 提取每条评论
    reviewElements.forEach((review, index) => {
      if (index >= 20) return; // 最多提取20条

      const reviewData = extractReviewFromElement(review);
      if (reviewData) {
        reviews.push(reviewData);
      }
    });
  }

  // 只保留差评（1-2星）
  const negativeReviews = reviews.filter(review => review.rating > 0 && review.rating <= 2);

  // 如果没有找到差评，返回提示信息
  if (negativeReviews.length === 0) {
    console.log('未找到差评');
    return [{
      title: '提示',
      content: reviews.length > 0
        ? `找到 ${reviews.length} 条评论，但没有差评（1-2星）`
        : '未找到评论。Amazon页面可能需要先点击"查看所有评论"按钮，或者页面结构不支持自动提取。',
      rating: 0,
      date: ''
    }];
  }

  return negativeReviews;
}

/**
 * 从单个评论元素提取评论数据
 * @param {Element} review - 评论元素
 * @returns {Object|null} 评论数据
 */
function extractReviewFromElement(review) {
  try {
    const reviewData = {
      title: '',
      content: '',
      rating: 0,
      date: ''
    };

    // 提取评论标题 - 多种选择器
    const titleSelectors = [
      '[data-hook="review-title"]',
      '.review-title',
      '.a-size-base.review-title',
      'a[data-hook="review-title"]',
      '.a-size-base'
    ];

    for (const selector of titleSelectors) {
      const titleElement = review.querySelector(selector);
      if (titleElement && titleElement.textContent.trim()) {
        reviewData.title = titleElement.textContent.trim();
        break;
      }
    }

    // 提取评论内容 - 多种选择器
    const contentSelectors = [
      '[data-hook="review-body"]',
      '.review-text',
      '.a-size-base.review-text',
      'span[data-hook="review-body"]',
      '.a-expander-content'
    ];

    for (const selector of contentSelectors) {
      const contentElement = review.querySelector(selector);
      if (contentElement && contentElement.textContent.trim()) {
        reviewData.content = contentElement.textContent.trim();
        break;
      }
    }

    // 提取评分 - 多种方法
    const ratingSelectors = [
      '[data-hook="review-star-rating"]',
      '.review-rating',
      '.a-icon-alt',
      '[data-hook="cmps-review-star-rating"]'
    ];

    for (const selector of ratingSelectors) {
      const ratingElement = review.querySelector(selector);
      if (ratingElement) {
        const ratingText = ratingElement.textContent || ratingElement.getAttribute('alt') || '';
        const ratingMatch = ratingText.match(/(\d\.?\d?)\s*out\s*of\s*5/) ||
                           ratingText.match(/(\d\.?\d?)\s*星/) ||
                           ratingText.match(/^(\d\.?\d?)/);
        if (ratingMatch) {
          reviewData.rating = Math.round(parseFloat(ratingMatch[1]));
          break;
        }
      }
    }

    // 提取日期 - 多种选择器
    const dateSelectors = [
      '[data-hook="review-date"]',
      '.review-date',
      '.a-size-base.a-color-secondary.review-date',
      'span[data-hook="review-date"]'
    ];

    for (const selector of dateSelectors) {
      const dateElement = review.querySelector(selector);
      if (dateElement && dateElement.textContent.trim()) {
        reviewData.date = dateElement.textContent.trim();
        break;
      }
    }

    // 只返回有内容的评论
    if (reviewData.content || reviewData.title) {
      return reviewData;
    }

    return null;
  } catch (error) {
    console.error('提取评论元素失败:', error);
    return null;
  }
}