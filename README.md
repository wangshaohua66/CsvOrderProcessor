# CSV Order Processor - 使用说明

## 📋 目录
- [快速开始](#快速开始)
- [命令行用法](#命令行用法)
- [编程接口](#编程接口)
- [输入格式](#输入格式)
- [输出格式](#输出格式)
- [配置选项](#配置选项)
- [示例场景](#示例场景)
- [故障排查](#故障排查)

---

## 快速开始

### 1. 基本用法

```bash
# 处理单个订单文件
python3 src/main.py orders.csv processed_orders.csv

# 指定库存文件
python3 src/main.py orders.csv processed_orders.csv --inventory stock.csv

# 转换货币为欧元
python3 src/main.py orders.csv processed_orders.csv --currency EUR
```

### 2. 批量处理

```bash
# 处理目录中的所有CSV文件
python3 src/main.py ./input_directory ./output_directory --batch
```

---

## 命令行用法

### 语法

```bash
python3 main.py <input> <output> [OPTIONS]
```

### 参数

| 参数 | 说明 | 必需 |
|------|------|------|
| `input` | 输入CSV文件或目录 | ✅ |
| `output` | 输出CSV文件或目录 | ✅ |

### 选项

| 选项 | 简写 | 说明 | 默认值 |
|------|------|------|--------|
| `--inventory` | `-i` | 库存CSV文件路径 | 无 |
| `--currency` | `-c` | 目标货币代码 | USD |
| `--batch` | | 批量处理目录中的所有CSV | False |
| `--report` | `-r` | 生成JSON报告文件 | 无 |

### 完整示例

```bash
# 示例1: 基本处理
python3 main.py orders_jan.csv orders_jan_processed.csv

# 示例2: 带库存检查
python3 main.py orders.csv output.csv \
    --inventory warehouse_stock.csv

# 示例3: 货币转换 + 生成报告
python3 main.py international_orders.csv converted_orders.csv \
    --currency EUR \
    --report conversion_report.json

# 示例4: 批量处理
python3 main.py ./daily_orders ./processed_orders \
    --batch \
    --inventory stock.csv \
    --currency USD
```

---

## 编程接口

### 基本用法

```python
from main import OrderProcessor

# 创建处理器实例
config = {
    'inventory_file': 'stock.csv'  # 可选
}
processor = OrderProcessor(config)

# 处理单个文件
stats = processor.process_file(
    input_file='orders.csv',
    output_file='output.csv',
    target_currency='USD'
)

# 查看统计
print(f"处理了 {stats['total_orders']} 个订单")
print(f"有效订单: {stats['valid_orders']}")
print(f"无效订单: {stats['invalid_orders']}")
print(f"重复订单: {stats['duplicates_merged']}")
```

### 批量处理

```python
from main import OrderProcessor

processor = OrderProcessor({'inventory_file': 'stock.csv'})

# 处理多个文件
input_files = ['orders1.csv', 'orders2.csv', 'orders3.csv']
results = processor.process_batch(
    input_files=input_files,
    output_dir='./output',
    target_currency='USD'
)

# 查看每个文件的结果
for result in results:
    if 'error' in result:
        print(f"❌ {result['input_file']}: {result['error']}")
    else:
        print(f"✅ {result['input_file']}: {result['valid_orders']} 订单")
```

### 获取详细报告

```python
from main import OrderProcessor
import json

processor = OrderProcessor({})
processor.process_file('orders.csv', 'output.csv')

# 生成摘要报告
report = processor.get_summary_report()
print(json.dumps(report, indent=2))
```

输出示例：
```json
{
  "summary": {
    "total_processed": 150,
    "successful": 142,
    "failed": 8,
    "duplicates_removed": 5,
    "inventory_issues": 3,
    "success_rate": 94.67
  },
  "errors": [
    "Invalid email format: not-an-email",
    "Insufficient inventory for PROD001: requested 10, available 5"
  ],
  "warnings": [
    "Unsupported currency: XYZ"
  ]
}
```

---

## 输入格式

### 订单CSV文件格式

#### 必需列

| 列名 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `order_id` | 字符串 | 订单唯一标识 | ORD001 |
| `customer_email` | 字符串 | 客户邮箱 | alice@example.com |
| `product_id` | 字符串 | 产品SKU/ID | PROD001 |
| `quantity` | 整数 | 购买数量（必须>0） | 2 |
| `unit_price` | 小数 | 单价 | 29.99 |
| `currency` | 字符串 | 货币代码 | USD, EUR, GBP, CNY, JPY, CAD, AUD |
| `order_date` | 日期 | 订单日期（多种格式） | 2024-01-15 |

#### 可选列

| 列名 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `status` | 字符串 | 订单状态 | pending, processing, shipped, delivered, cancelled, refunded |
| `shipping_address` | 字符串 | 收货地址 | 123 Main St, New York |

#### 支持的日期格式

系统可以自动识别以下日期格式：
- `YYYY-MM-DD` (2024-01-15)
- `YYYY/MM/DD` (2024/01/15)
- `MM/DD/YYYY` (01/15/2024)
- `DD-MM-YYYY` (15-01-2024)
- `YYYY-MM-DD HH:MM:SS` (2024-01-15 10:30:00)
- ISO 8601 (2024-01-15T10:30:00Z)

#### 示例订单文件

```csv
order_id,customer_email,product_id,quantity,unit_price,currency,order_date,status,shipping_address
ORD001,alice@example.com,PROD001,2,29.99,USD,2024-01-15,pending,"123 Main St, NY"
ORD002,bob@example.com,PROD002,1,49.99,EUR,2024-01-16,processing,"456 Oak Ave, London"
ORD003,charlie@example.com,PROD003,5,15.50,CNY,2024-01-17,pending,"789 Pine Rd, Beijing"
```

### 库存CSV文件格式

#### 列定义

| 列名 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `product_id` | 字符串 | 产品SKU/ID | PROD001 |
| `quantity` | 整数 | 可用库存 | 100 |

#### 示例库存文件

```csv
product_id,quantity
PROD001,100
PROD002,50
PROD003,200
PROD004,0
```

---

## 输出格式

### 输出CSV文件

输出文件包含所有输入列，以及以下新增列：

| 列名 | 说明 | 示例 |
|------|------|------|
| `total_amount` | 订单总额（单价×数量） | 59.98 |
| `original_currency` | 原始货币（如果发生转换） | EUR |
| `exchange_rate_applied` | 是否应用汇率 | yes/no |
| `inventory_reserved` | 库存是否已预留 | yes/no |
| `fulfillment_status` | 履约状态 | ready |

### 输出示例

```csv
order_id,customer_email,product_id,quantity,unit_price,total_amount,currency,original_currency,exchange_rate_applied,order_date,status,inventory_reserved,fulfillment_status
ORD001,alice@example.com,PROD001,2,29.99,59.98,USD,,,2024-01-15,pending,yes,ready
ORD002,bob@example.com,PROD002,1,54.34,54.34,USD,EUR,yes,2024-01-16,processing,yes,ready
```

**注意**：
- 如果原始货币与目标货币相同，`original_currency`和`exchange_rate_applied`为空
- 无效的订单不会出现在输出中
- 重复的订单只保留第一条记录

---

## 配置选项

### OrderProcessor配置字典

```python
config = {
    'inventory_file': 'stock.csv'  # 库存文件路径（可选）
}
```

### 支持的货币代码

```python
SUPPORTED_CURRENCIES = {
    'USD': 'US Dollar',
    'EUR': 'Euro',
    'GBP': 'British Pound',
    'CNY': 'Chinese Yuan',
    'JPY': 'Japanese Yen',
    'CAD': 'Canadian Dollar',
    'AUD': 'Australian Dollar'
}
```

### 汇率说明

当前使用固定汇率（实际生产环境应从API获取）：
- 1 USD = 0.92 EUR
- 1 USD = 0.79 GBP
- 1 USD = 7.24 CNY
- 1 USD = 150.25 JPY
- 1 USD = 1.36 CAD
- 1 USD = 1.53 AUD

---

## 示例场景

### 场景1: 单渠道订单处理

```bash
# Shopify每日订单导出处理
python3 main.py shopify_orders_20240115.csv processed.csv \
    --inventory current_stock.csv \
    --currency USD \
    --report daily_report.json
```

### 场景2: 多渠道订单整合

```bash
# 合并多个渠道的订单
mkdir -p combined_orders
cp shopify_orders.csv combined_orders/
cp amazon_orders.csv combined_orders/
cp offline_orders.csv combined_orders/

python3 main.py combined_orders/ processed_output/ \
    --batch \
    --inventory master_inventory.csv \
    --currency USD
```

### 场景3: 国际订单货币统一

```bash
# 将所有订单转换为美元便于财务统计
python3 main.py international_orders.csv usd_orders.csv \
    --currency USD \
    --report currency_conversion_summary.json
```

### 场景4: 库存预检查

```bash
# 在处理前检查哪些订单会因库存不足失败
python3 << 'EOF'
from main import OrderProcessor

processor = OrderProcessor({'inventory_file': 'stock.csv'})
stats = processor.process_file('orders.csv', 'output.csv')

print(f"库存不足的订单数: {stats['inventory_failures']}")
for error in stats['errors']:
    if 'Insufficient inventory' in error:
        print(f"  - {error}")
EOF
```

### 场景5: 编程方式集成到ETL流程

```python
from main import OrderProcessor
import pandas as pd

def process_daily_orders(date_str):
    """每日订单处理任务"""
    # 初始化处理器
    processor = OrderProcessor({
        'inventory_file': f'/data/inventory/{date_str}.csv'
    })
    
    # 处理订单
    input_file = f'/data/orders/{date_str}.csv'
    output_file = f'/data/processed/{date_str}.csv'
    
    stats = processor.process_file(input_file, output_file, 'USD')
    
    # 记录日志
    log_processing_stats(date_str, stats)
    
    # 如果有库存问题，发送警报
    if stats['inventory_failures'] > 0:
        send_alert(f"{stats['inventory_failures']} orders failed inventory check")
    
    return stats

# 运行
process_daily_orders('2024-01-15')
```

---

## 故障排查

### 常见问题

#### 1. "Input file not found"

**原因**: 输入文件路径错误  
**解决**: 
```bash
# 检查文件是否存在
ls -l orders.csv

# 使用绝对路径
python3 main.py /absolute/path/to/orders.csv output.csv
```

#### 2. "Not a git repository" (如果使用git-stats-analyzer)

**原因**: 在非Git目录运行  
**解决**: 切换到有效的Git仓库目录

#### 3. "Invalid JSON response"

**原因**: API返回格式错误  
**解决**: 检查网络连接和API端点

#### 4. 订单被标记为重复

**原因**: 相同的order_id + product_id组合出现多次  
**解决**: 
- 检查源数据是否有真正的重复
- 如果同一订单有多个产品，确保product_id不同

#### 5. 库存检查失败

**原因**: 库存文件中缺少产品或数量为0  
**解决**:
```bash
# 检查库存文件
cat stock.csv | grep PROD001

# 更新库存
echo "PROD001,100" >> stock.csv
```

#### 6. 货币转换错误

**原因**: 使用了不支持的货币代码  
**解决**: 使用支持的货币代码：USD, EUR, GBP, CNY, JPY, CAD, AUD

### 调试模式

启用详细日志输出：

```python
import logging
logging.getLogger('main').setLevel(logging.DEBUG)
```

或在命令行：

```bash
python3 main.py orders.csv output.csv 2>&1 | tee debug.log
```

### 性能优化建议

1. **大文件处理**: 系统已使用流式处理，可处理GB级文件
2. **批量处理**: 使用`--batch`模式比逐个文件处理更高效
3. **内存优化**: 避免一次性加载整个文件到内存
4. **并发处理**: InventoryManager和CurrencyConverter都是线程安全的

### 获取帮助

```bash
# 显示命令行帮助
python3 main.py --help

# 查看详细文档
cat README.md
cat USAGE.md
```

---

## API参考

### OrderProcessor类

#### 构造函数

```python
OrderProcessor(config: Dict)
```

**参数**:
- `config`: 配置字典
  - `inventory_file` (可选): 库存CSV文件路径

#### process_file方法

```python
process_file(input_file: str, output_file: str, target_currency: str = 'USD') -> Dict
```

**参数**:
- `input_file`: 输入CSV文件路径
- `output_file`: 输出CSV文件路径
- `target_currency`: 目标货币代码

**返回**: 处理统计字典

#### process_batch方法

```python
process_batch(input_files: List[str], output_dir: str, target_currency: str = 'USD') -> List[Dict]
```

**参数**:
- `input_files`: 输入文件路径列表
- `output_dir`: 输出目录
- `target_currency`: 目标货币代码

**返回**: 每个文件的处理结果列表

#### get_summary_report方法

```python
get_summary_report() -> Dict
```

**返回**: 处理摘要报告

### CurrencyConverter类

#### convert方法

```python
convert(amount: Decimal, from_currency: str, to_currency: str = 'USD') -> Decimal
```

**参数**:
- `amount`: 金额（Decimal类型）
- `from_currency`: 源货币代码
- `to_currency`: 目标货币代码

**返回**: 转换后的金额

### OrderValidator类

#### validate_order方法

```python
validate_order(order: Dict, row_number: int) -> List[str]
```

**参数**:
- `order`: 订单数据字典
- `row_number`: CSV行号

**返回**: 验证错误列表（空列表表示通过）

### InventoryManager类

#### check_availability方法

```python
check_availability(product_id: str, requested_quantity: int) -> Tuple[bool, int]
```

**参数**:
- `product_id`: 产品ID
- `requested_quantity`: 请求数量

**返回**: (是否有货, 实际可用数量)

#### reserve_stock方法

```python
reserve_stock(product_id: str, quantity: int) -> bool
```

**参数**:
- `product_id`: 产品ID
- `quantity`: 要预留的数量

**返回**: 是否成功预留

---

## 最佳实践

### 1. 数据准备

- 清理源数据中的空行
- 确保日期格式一致
- 验证邮箱格式
- 检查货币代码拼写

### 2. 库存管理

- 定期同步库存数据
- 设置安全库存阈值
- 监控库存不足的订单

### 3. 错误处理

- 始终检查返回的统计信息
- 记录并审查验证错误
- 对失败的订单进行人工复核

### 4. 性能优化

- 大批量数据分批处理
- 使用SSD存储临时文件
- 监控系统资源使用情况

### 5. 安全考虑

- 不要在生产环境中硬编码API密钥
- 定期备份库存数据
- 审计订单处理日志

---

## 版本历史

### v1.0 (2026-04-16)
- 初始版本
- 支持基本的订单处理功能
- 实现货币转换、库存检查、重复检测
- 提供完整的测试套件

---

## 支持与反馈

如有问题或建议：
1. 查看 `README.md` 获取项目概述
2. 查看 `QUICKSTART.md` 获取快速开始指南
3. 阅读 `bugs/` 目录了解已知问题和修复方案

---

**最后更新**: 2026-04-16  
**维护者**: AI Benchmark Suite Team
