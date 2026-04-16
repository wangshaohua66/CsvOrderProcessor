#!/usr/bin/env python3
"""
测试脚本：验证所有Bug修复效果
"""

import os
import sys
import tempfile
import shutil
from decimal import Decimal
from datetime import datetime
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from main import (
    CurrencyConverter, OrderValidator, InventoryManager, 
    OrderProcessor, OrderProcessingError
)


class TestResults:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []
    
    def add_pass(self, test_name):
        self.passed += 1
        print(f"✅ PASS: {test_name}")
    
    def add_fail(self, test_name, reason):
        self.failed += 1
        self.errors.append((test_name, reason))
        print(f"❌ FAIL: {test_name}")
        print(f"   原因: {reason}")
    
    def print_summary(self):
        total = self.passed + self.failed
        print("\n" + "="*60)
        print(f"测试总结: {self.passed}/{total} 通过")
        if self.failed > 0:
            print("\n失败的测试:")
            for name, reason in self.errors:
                print(f"  - {name}: {reason}")
        print("="*60)


def test_bug1_currency_precision():
    """测试Bug 1: 货币转换精度问题"""
    print("\n" + "="*60)
    print("测试 Bug 1: 货币转换精度")
    print("="*60)
    
    results = TestResults()
    converter = CurrencyConverter()
    
    # 测试1: 基本转换精度
    amount = Decimal('29.99')
    converted = converter.convert(amount, 'USD', 'EUR')
    expected = Decimal('27.59')  # 29.99 * 0.92 = 27.5908 → 27.59
    if converted == expected:
        results.add_pass("基本货币转换精度")
    else:
        results.add_fail("基本货币转换精度", f"期望 {expected}, 得到 {converted}")
    
    # 测试2: 大金额转换精度
    large_amount = Decimal('12345.67')
    converted_large = converter.convert(large_amount, 'USD', 'EUR')
    # 12345.67 * 0.92 = 11358.0164 → 11358.02
    expected_large = Decimal('11358.02')
    if converted_large == expected_large:
        results.add_pass("大金额转换精度正确")
    else:
        results.add_fail("大金额转换精度正确", f"期望 {expected_large}, 得到 {converted_large}")
    
    # 测试3: 往返转换精度
    original = Decimal('100.00')
    to_eur = converter.convert(original, 'USD', 'EUR')
    back_to_usd = converter.convert(to_eur, 'EUR', 'USD')
    if back_to_usd == original:
        results.add_pass("往返转换精度保持")
    else:
        results.add_fail("往返转换精度保持", f"期望 {original}, 得到 {back_to_usd}")
    
    return results


def test_bug2_duplicate_detection():
    """测试Bug 2: 重复订单检测"""
    print("\n" + "="*60)
    print("测试 Bug 2: 重复订单检测")
    print("="*60)
    
    results = TestResults()
    
    # 创建临时库存文件
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        f.write("product_id,quantity\n")
        f.write("PROD001,100\n")
        f.write("PROD002,50\n")
        f.write("PROD003,30\n")
        inventory_file = f.name
    
    # 创建临时订单文件
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        f.write("order_id,customer_email,product_id,quantity,unit_price,currency,order_date,status\n")
        f.write("ORD001,alice@test.com,PROD001,2,29.99,USD,2024-01-15,pending\n")
        f.write("ORD001,alice@test.com,PROD002,1,49.99,USD,2024-01-15,pending\n")
        f.write("ORD001,alice@test.com,PROD003,3,19.99,USD,2024-01-15,pending\n")
        orders_file = f.name
    
    try:
        config = {'inventory_file': inventory_file}
        processor = OrderProcessor(config)
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            output_file = f.name
        
        stats = processor.process_file(orders_file, output_file)
        
        # 应该处理3个订单（同一订单的3个不同商品）
        if stats['valid_orders'] == 3:
            results.add_pass("同一订单多个商品正确处理")
        else:
            results.add_fail("同一订单多个商品正确处理", 
                           f"期望3个有效订单，得到{stats['valid_orders']}个")
        
        # 检查重复计数
        if stats['duplicates_merged'] == 0:
            results.add_pass("无错误重复检测")
        else:
            results.add_fail("无错误重复检测", 
                           f"重复计数应为0，得到{stats['duplicates_merged']}")
        
        os.remove(output_file)
    finally:
        os.remove(inventory_file)
        os.remove(orders_file)
    
    return results


def test_bug3_temp_file_cleanup():
    """测试Bug 3: 临时文件清理"""
    print("\n" + "="*60)
    print("测试 Bug 3: 临时文件清理")
    print("="*60)
    
    results = TestResults()
    
    # 创建一个会导致错误的订单文件
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        f.write("order_id,customer_email,product_id,quantity,unit_price,currency,order_date\n")
        f.write("ORD001,alice@test.com,PROD001,invalid_qty,29.99,USD,2024-01-15\n")  # 无效数量
        orders_file = f.name
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        f.write("product_id,quantity\nPROD001,100\n")
        inventory_file = f.name
    
    output_dir = tempfile.mkdtemp()
    
    try:
        config = {'inventory_file': inventory_file}
        processor = OrderProcessor(config)
        output_file = os.path.join(output_dir, 'output.csv')
        
        # 统计临时文件数量
        temp_files_before = [f for f in os.listdir(output_dir) if f.endswith('.csv')]
        
        try:
            processor.process_file(orders_file, output_file)
        except:
            pass  # 预期会失败
        
        temp_files_after = [f for f in os.listdir(output_dir) if f.endswith('.csv')]
        
        # 应该只有输出文件，没有遗留的临时文件
        if len(temp_files_after) <= 1:  # 最多只有输出文件
            results.add_pass("异常时临时文件被清理")
        else:
            results.add_fail("异常时临时文件被清理", 
                           f"发现{len(temp_files_after)}个文件，可能有临时文件泄漏")
    
    finally:
        os.remove(orders_file)
        os.remove(inventory_file)
        shutil.rmtree(output_dir)
    
    return results


def test_bug4_inventory_race_condition():
    """测试Bug 4: 库存竞态条件"""
    print("\n" + "="*60)
    print("测试 Bug 4: 库存竞态条件")
    print("="*60)
    
    results = TestResults()
    
    # 创建库存管理器，初始库存为10
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        f.write("product_id,quantity\nPROD001,10\n")
        inventory_file = f.name
    
    try:
        manager = InventoryManager(inventory_file)
        
        success_count = [0]
        fail_count = [0]
        lock = threading.Lock()
        
        def try_reserve():
            success, _ = manager.check_and_reserve_stock('PROD001', 10)
            with lock:
                if success:
                    success_count[0] += 1
                else:
                    fail_count[0] += 1
        
        # 同时启动10个线程尝试预订
        threads = []
        for i in range(10):
            t = threading.Thread(target=try_reserve)
            threads.append(t)
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # 应该只有1个成功，9个失败
        if success_count[0] == 1:
            results.add_pass("并发预订只有一个成功")
        else:
            results.add_fail("并发预订只有一个成功", 
                           f"期望1个成功，得到{success_count[0]}个")
        
        if fail_count[0] == 9:
            results.add_pass("并发预订九个失败")
        else:
            results.add_fail("并发预订九个失败", 
                           f"期望9个失败，得到{fail_count[0]}个")
        
        # 检查最终库存
        final_stock = manager.get_stock_level('PROD001')
        if final_stock == 0:
            results.add_pass("库存未被扣成负数")
        else:
            results.add_fail("库存未被扣成负数", 
                           f"库存应为0，实际为{final_stock}")
    
    finally:
        os.remove(inventory_file)
    
    return results


def test_bug5_date_parsing():
    """测试Bug 5: 日期解析歧义"""
    print("\n" + "="*60)
    print("测试 Bug 5: 日期解析")
    print("="*60)
    
    results = TestResults()
    
    # 测试ISO格式优先
    iso_date = OrderValidator._parse_date('2024-01-15')
    if iso_date.year == 2024 and iso_date.month == 1 and iso_date.day == 15:
        results.add_pass("ISO格式日期解析正确")
    else:
        results.add_fail("ISO格式日期解析正确", 
                       f"期望2024-01-15，得到{iso_date}")
    
    # 测试带斜杠的年月日格式
    ymd_date = OrderValidator._parse_date('2024/01/15')
    if ymd_date.year == 2024 and ymd_date.month == 1 and ymd_date.day == 15:
        results.add_pass("YYYY/MM/DD格式解析正确")
    else:
        results.add_fail("YYYY/MM/DD格式解析正确", 
                       f"期望2024-01-15，得到{ymd_date}")
    
    # 测试欧洲格式（应该放在最后）
    eu_date = OrderValidator._parse_date('15-01-2024')
    if eu_date.year == 2024 and eu_date.month == 1 and eu_date.day == 15:
        results.add_pass("欧洲DD-MM-YYYY格式解析正确")
    else:
        results.add_fail("欧洲DD-MM-YYYY格式解析正确", 
                       f"期望2024-01-15，得到{eu_date}")
    
    return results


def test_bug6_required_field_validation():
    """测试Bug 6: 必填字段验证"""
    print("\n" + "="*60)
    print("测试 Bug 6: 必填字段验证")
    print("="*60)
    
    results = TestResults()
    
    # 测试空字符串被检测
    order_empty_email = {
        'order_id': 'ORD001',
        'customer_email': '',  # 空字符串
        'product_id': 'PROD001',
        'quantity': '1',
        'unit_price': '29.99',
        'currency': 'USD',
        'order_date': '2024-01-15'
    }
    
    errors = OrderValidator.validate_order(order_empty_email, 1)
    has_email_error = any('customer_email' in e for e in errors)
    
    if has_email_error:
        results.add_pass("空字符串邮箱被检测")
    else:
        results.add_fail("空字符串邮箱被检测", 
                       "空字符串应该被识别为缺失字段")
    
    # 测试纯空白字符被检测
    order_whitespace = {
        'order_id': 'ORD002',
        'customer_email': '   ',  # 纯空白
        'product_id': 'PROD001',
        'quantity': '1',
        'unit_price': '29.99',
        'currency': 'USD',
        'order_date': '2024-01-15'
    }
    
    errors = OrderValidator.validate_order(order_whitespace, 2)
    has_email_error = any('customer_email' in e for e in errors)
    
    if has_email_error:
        results.add_pass("纯空白字符被检测")
    else:
        results.add_fail("纯空白字符被检测", 
                       "纯空白字符应该被识别为缺失字段")
    
    # 测试正常数据通过
    order_valid = {
        'order_id': 'ORD003',
        'customer_email': 'test@example.com',
        'product_id': 'PROD001',
        'quantity': '1',
        'unit_price': '29.99',
        'currency': 'USD',
        'order_date': '2024-01-15'
    }
    
    errors = OrderValidator.validate_order(order_valid, 3)
    
    if len(errors) == 0:
        results.add_pass("正常数据验证通过")
    else:
        results.add_fail("正常数据验证通过", 
                       f"正常数据不应有错误，但得到: {errors}")
    
    return results


def main():
    print("\n" + "="*60)
    print("订单处理系统Bug修复验证测试")
    print("="*60)
    
    all_results = []
    
    # 运行所有测试
    all_results.append(test_bug1_currency_precision())
    all_results.append(test_bug2_duplicate_detection())
    all_results.append(test_bug3_temp_file_cleanup())
    all_results.append(test_bug4_inventory_race_condition())
    all_results.append(test_bug5_date_parsing())
    all_results.append(test_bug6_required_field_validation())
    
    # 汇总结果
    total_passed = sum(r.passed for r in all_results)
    total_failed = sum(r.failed for r in all_results)
    total_tests = total_passed + total_failed
    
    print("\n" + "="*60)
    print("总体测试结果")
    print("="*60)
    print(f"总测试数: {total_tests}")
    print(f"通过: {total_passed}")
    print(f"失败: {total_failed}")
    print(f"通过率: {total_passed/total_tests*100:.1f}%")
    
    if total_failed > 0:
        print("\n❌ 存在失败的测试，请检查修复")
        return 1
    else:
        print("\n✅ 所有测试通过！Bug修复成功！")
        return 0


if __name__ == '__main__':
    sys.exit(main())
