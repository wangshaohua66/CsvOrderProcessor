#!/usr/bin/env python3
"""
E-commerce Order Processing System

A production-grade CSV order processing tool that handles:
- Multi-format date parsing and normalization
- Currency conversion with precision handling
- Duplicate detection and merge logic
- Inventory validation against stock levels
- Batch processing with memory-efficient streaming
- Comprehensive audit logging
- Error recovery and partial result preservation

Real-world scenario: Process daily order exports from multiple sales channels
(Shopify, Amazon, offline stores) into a unified format for warehouse fulfillment.
"""

import csv
import sys
import os
import json
import hashlib
import tempfile
import shutil
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Dict, List, Optional, Iterator, Tuple, Set
from collections import defaultdict
from contextlib import contextmanager
import logging
import threading

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class OrderProcessingError(Exception):
    """Base exception for order processing errors."""
    def __init__(self, message: str, order_id: Optional[str] = None,
                 row_number: Optional[int] = None):
        super().__init__(message)
        self.order_id = order_id
        self.row_number = row_number


class ValidationError(OrderProcessingError):
    """Data validation failed."""
    pass


class InventoryError(OrderProcessingError):
    """Insufficient inventory."""
    def __init__(self, message: str, product_id: str, requested: int,
                 available: int):
        super().__init__(message)
        self.product_id = product_id
        self.requested = requested
        self.available = available


class CurrencyConverter:
    """Thread-safe currency conversion with cached rates."""

    # Exchange rates relative to USD (would be fetched from API in production)
    EXCHANGE_RATES = {
        'USD': 1.0,
        'EUR': 0.92,
        'GBP': 0.79,
        'CNY': 7.24,
        'JPY': 150.25,
        'CAD': 1.36,
        'AUD': 1.53,
    }

    _instance_lock = threading.Lock()
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._cache = {}
        self._cache_lock = threading.Lock()

    def convert(self, amount: Decimal, from_currency: str,
                to_currency: str = 'USD') -> Decimal:
        """Convert amount between currencies with precision."""
        if from_currency == to_currency:
            return amount

        cache_key = f"{from_currency}_{to_currency}"

        with self._cache_lock:
            if cache_key in self._cache:
                rate = self._cache[cache_key]
            else:
                # Calculate cross rate through USD
                from_rate = self.EXCHANGE_RATES.get(from_currency)
                to_rate = self.EXCHANGE_RATES.get(to_currency)

                if from_rate is None or to_rate is None:
                    raise ValueError(
                        f"Unsupported currency: {from_currency} or {to_currency}"
                    )

                rate = Decimal(str(to_rate)) / Decimal(str(from_rate))
                self._cache[cache_key] = rate

        # Convert using Decimal to maintain precision
        converted = amount * rate
        return converted.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


class OrderValidator:
    """Validate order data against business rules."""

    REQUIRED_FIELDS = ['order_id', 'customer_email', 'product_id',
                      'quantity', 'unit_price', 'currency', 'order_date']

    VALID_STATUSES = ['pending', 'processing', 'shipped', 'delivered',
                     'cancelled', 'refunded']

    EMAIL_REGEX = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'

    @classmethod
    def validate_order(cls, order: Dict, row_number: int) -> List[str]:
        """Validate a single order record. Returns list of validation errors."""
        errors = []

        # Check required fields
        for field in cls.REQUIRED_FIELDS:
            value = order.get(field)

            if value is None or (isinstance(value, str) and value.strip() == ''):
                errors.append(f"Missing required field: {field}")

        # Validate email format
        email = order.get('customer_email', '')
        if email and not cls._validate_email(str(email)):
            errors.append(f"Invalid email format: {email}")

        # Validate quantity
        try:
            quantity = int(order.get('quantity', 0))
            if quantity <= 0:
                errors.append(f"Quantity must be positive: {quantity}")
        except (ValueError, TypeError):
            errors.append(f"Invalid quantity: {order.get('quantity')}")

        # Validate price
        try:
            price = Decimal(str(order.get('unit_price', '0')))
            if price < 0:
                errors.append(f"Price cannot be negative: {price}")
        except (InvalidOperation, ValueError):
            errors.append(f"Invalid price: {order.get('unit_price')}")

        # Validate currency
        currency = order.get('currency', '')
        if currency and currency not in CurrencyConverter.EXCHANGE_RATES:
            errors.append(f"Unsupported currency: {currency}")

        # Validate status
        status = order.get('status', 'pending')
        if status not in cls.VALID_STATUSES:
            errors.append(f"Invalid status: {status}")

        # Validate date
        date_str = order.get('order_date', '')
        if date_str:
            try:
                cls._parse_date(str(date_str))
            except ValueError as e:
                errors.append(f"Invalid date format: {date_str} - {e}")

        return errors

    @classmethod
    def _validate_email(cls, email: str) -> bool:
        """Basic email validation."""
        import re
        return bool(re.match(cls.EMAIL_REGEX, email))

    @classmethod
    def _parse_date(cls, date_str: str) -> datetime:
        """Parse date from multiple formats with region detection."""
        date_str = date_str.strip()

        # ISO 8601 formats (unambiguous, try first)
        iso_formats = [
            '%Y-%m-%d',
            '%Y/%m/%d',
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%dT%H:%M:%S',
            '%Y-%m-%dT%H:%M:%SZ',
        ]

        for fmt in iso_formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue

        # Ambiguous formats - try to detect based on values
        # If day > 12, it must be day-first (European format)
        # If month > 12, it must be month-first (US format)
        for sep in ['/', '-']:
            if sep in date_str:
                parts = date_str.split(sep)
                if len(parts) == 3:
                    try:
                        first = int(parts[0])
                        second = int(parts[1])

                        # If first number > 12, it's day-first (European)
                        if first > 12:
                            try:
                                return datetime.strptime(date_str, f'%d{sep}%m{sep}%Y')
                            except ValueError:
                                pass
                        # If second number > 12, it's month-first (US)
                        elif second > 12:
                            try:
                                return datetime.strptime(date_str, f'%m{sep}%d{sep}%Y')
                            except ValueError:
                                pass
                    except ValueError:
                        pass

        # Fallback: try standard formats with preference for ISO (year-first)
        fallback_formats = [
            '%d/%m/%Y',
            '%d-%m-%Y',
            '%m/%d/%Y',
            '%m-%d-%Y',
        ]

        for fmt in fallback_formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue

        raise ValueError(f"Unable to parse date: {date_str}")


class InventoryManager:
    """Manage product inventory with thread-safe operations."""

    def __init__(self, inventory_file: Optional[str] = None):
        self._inventory = {}
        self._lock = threading.RLock()

        if inventory_file and os.path.exists(inventory_file):
            self.load_inventory(inventory_file)

    def load_inventory(self, inventory_file: str):
        """Load inventory from CSV file."""
        with open(inventory_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                product_id = row['product_id']
                quantity = int(row['quantity'])
                self._inventory[product_id] = quantity

        logger.info(f"Loaded {len(self._inventory)} products from inventory")

    def check_and_reserve(self, product_id: str,
                          requested_quantity: int) -> Tuple[bool, int]:
        """
        Atomically check availability and reserve stock.
        Returns (success, actual_reserved_quantity).
        """
        with self._lock:
            available = self._inventory.get(product_id, 0)
            if available >= requested_quantity:
                self._inventory[product_id] -= requested_quantity
                return True, requested_quantity
            elif available > 0:
                # Partial fulfillment - reserve what is available
                self._inventory[product_id] = 0
                return False, available
            else:
                return False, 0

    def check_availability(self, product_id: str,
                          requested_quantity: int) -> Tuple[bool, int]:
        """Check if product is available. Returns (available, actual_quantity)."""
        with self._lock:
            available = self._inventory.get(product_id, 0)
            if available >= requested_quantity:
                return True, requested_quantity
            elif available > 0:
                return False, available
            else:
                return False, 0

    def reserve_stock(self, product_id: str, quantity: int) -> bool:
        """Reserve stock for an order. Returns True if successful."""
        with self._lock:
            available = self._inventory.get(product_id, 0)
            if available >= quantity:
                self._inventory[product_id] -= quantity
                return True
            return False

    def get_stock_level(self, product_id: str) -> int:
        """Get current stock level for a product."""
        with self._lock:
            return self._inventory.get(product_id, 0)

    def save_inventory(self, output_file: str):
        """Save current inventory state to CSV."""
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['product_id', 'quantity'])

            with self._lock:
                for product_id, quantity in sorted(self._inventory.items()):
                    writer.writerow([product_id, quantity])

        logger.info(f"Saved inventory to {output_file}")


class OrderProcessor:
    """
    Main order processing engine.

    Processes orders from multiple CSV files, validates data,
    checks inventory, converts currencies, and generates
    unified output for warehouse fulfillment.
    """

    def __init__(self, config: Dict):
        self.config = config
        self.currency_converter = CurrencyConverter()
        self.inventory = InventoryManager(config.get('inventory_file'))

        # Processing statistics
        self.stats = {
            'total_orders': 0,
            'valid_orders': 0,
            'invalid_orders': 0,
            'duplicates_merged': 0,
            'inventory_failures': 0,
            'errors': [],
            'warnings': []
        }

        # Thread safety for batch processing
        self._stats_lock = threading.Lock()
        self._processed_orders = []
        self._seen_orders = {}  # For duplicate detection

    def process_file(self, input_file: str, output_file: str,
                    target_currency: str = 'USD') -> Dict:
        """
        Process a single CSV order file.

        Args:
            input_file: Path to input CSV file
            output_file: Path to output CSV file
            target_currency: Currency to convert all prices to

        Returns:
            Processing statistics dictionary
        """
        if not os.path.exists(input_file):
            raise FileNotFoundError(f"Input file not found: {input_file}")

        logger.info(f"Processing file: {input_file}")

        # Reset stats for this file
        self.stats = {
            'total_orders': 0,
            'valid_orders': 0,
            'invalid_orders': 0,
            'duplicates_merged': 0,
            'inventory_failures': 0,
            'errors': [],
            'warnings': []
        }
        self._processed_orders = []
        self._seen_orders = {}

        # Detect encoding
        encoding = self._detect_encoding(input_file)
        logger.info(f"Detected encoding: {encoding}")

        # Process orders using streaming to handle large files
        temp_output = None
        try:
            # Create temporary output file
            temp_dir = os.path.dirname(output_file) or '.'
            temp_fd, temp_output = tempfile.mkstemp(
                suffix='.csv', dir=temp_dir
            )
            os.close(temp_fd)

            # Read and process orders
            orders = self._read_orders_streaming(input_file, encoding)

            # Write processed orders
            with open(temp_output, 'w', newline='', encoding='utf-8') as out_f:
                writer = None
                # Define complete fieldnames upfront to handle dynamic fields
                output_fieldnames = [
                    'order_id', 'customer_email', 'product_id', 'quantity',
                    'unit_price', 'total_amount', 'currency', 'original_currency',
                    'exchange_rate_applied', 'order_date', 'status',
                    'shipping_address', 'inventory_reserved', 'fulfillment_status'
                ]

                for order in orders:
                    self.stats['total_orders'] += 1

                    # Validate order
                    validation_errors = OrderValidator.validate_order(
                        order, self.stats['total_orders']
                    )

                    if validation_errors:
                        self.stats['invalid_orders'] += 1
                        self.stats['errors'].extend(validation_errors)
                        continue

                    # Check for duplicates
                    if self._is_duplicate(order):
                        self.stats['duplicates_merged'] += 1
                        continue

                    # Convert currency
                    try:
                        order = self._convert_order_currency(
                            order, target_currency
                        )
                    except ValueError as e:
                        self.stats['warnings'].append(str(e))
                        # Continue with original currency

                    # Check inventory
                    if not self._check_inventory(order):
                        self.stats['inventory_failures'] += 1
                        continue

                    # Mark order as seen
                    self._mark_order_seen(order)

                    # Write to output
                    if writer is None:
                        writer = csv.DictWriter(out_f, fieldnames=output_fieldnames,
                                              extrasaction='ignore')
                        writer.writeheader()

                    writer.writerow(order)
                    self.stats['valid_orders'] += 1
                    self._processed_orders.append(order)

            # Move temp file to final output
            if os.path.exists(output_file):
                os.remove(output_file)
            shutil.move(temp_output, output_file)
            temp_output = None

            logger.info(
                f"Processing complete: {self.stats['valid_orders']} valid, "
                f"{self.stats['invalid_orders']} invalid, "
                f"{self.stats['duplicates_merged']} duplicates"
            )

        except Exception as e:
            logger.error(f"Processing failed: {e}")
            raise
        finally:
            # Ensure temporary file is always cleaned up
            if temp_output and os.path.exists(temp_output):
                try:
                    os.remove(temp_output)
                    logger.info(f"Cleaned up temporary file: {temp_output}")
                except OSError as cleanup_error:
                    logger.warning(f"Failed to clean up temporary file {temp_output}: {cleanup_error}")



        return self.stats.copy()

    def process_batch(self, input_files: List[str], output_dir: str,
                     target_currency: str = 'USD') -> List[Dict]:
        """Process multiple order files."""
        results = []

        for input_file in input_files:
            base_name = os.path.basename(input_file)
            name_without_ext = os.path.splitext(base_name)[0]
            output_file = os.path.join(output_dir, f"{name_without_ext}_processed.csv")

            try:
                stats = self.process_file(input_file, output_file, target_currency)
                stats['input_file'] = input_file
                stats['output_file'] = output_file
                results.append(stats)
            except Exception as e:
                logger.error(f"Failed to process {input_file}: {e}")
                results.append({
                    'input_file': input_file,
                    'error': str(e)
                })

        return results

    def _detect_encoding(self, file_path: str) -> str:
        """Detect file encoding."""
        encodings = ['utf-8', 'gbk', 'gb2312', 'latin-1', 'utf-16']

        for enc in encodings:
            try:
                with open(file_path, 'r', encoding=enc) as f:
                    f.read(1024)
                return enc
            except (UnicodeDecodeError, UnicodeError):
                continue

        return 'utf-8'

    def _read_orders_streaming(self, file_path: str,
                               encoding: str) -> Iterator[Dict]:
        """Read orders from CSV file using streaming."""
        with open(file_path, 'r', encoding=encoding, errors='replace') as f:
            reader = csv.DictReader(f)

            for row in reader:
                # Clean up field values
                cleaned = {}
                for key, value in row.items():
                    if key:  # Skip None keys
                        cleaned[key.strip()] = value.strip() if value else ''

                yield cleaned

    def _is_duplicate(self, order: Dict) -> bool:
        """
        Detect duplicate orders based on order_id and product_id.

        An order is a duplicate only if both order_id and product_id match.
        This allows the same order to have multiple different products.
        """
        order_key = (order['order_id'], order['product_id'])

        if order_key in self._seen_orders:
            return True

        return False

    def _mark_order_seen(self, order: Dict):
        """Mark an order as processed."""
        order_key = (order['order_id'], order['product_id'])
        self._seen_orders[order_key] = {
            'timestamp': datetime.now().isoformat(),
            'quantity': int(order['quantity'])
        }

    def _convert_order_currency(self, order: Dict,
                                target_currency: str) -> Dict:
        """Convert order prices to target currency."""
        source_currency = order.get('currency', 'USD')

        if source_currency != target_currency:
            unit_price = Decimal(str(order['unit_price']))
            quantity = int(order['quantity'])

            # Calculate total in source currency first (higher precision)
            total_source = unit_price * quantity

            # Convert total amount to target currency (single conversion for accuracy)
            total = self.currency_converter.convert(
                total_source, source_currency, target_currency
            )

            # Convert unit price for display (may have rounding)
            converted_price = self.currency_converter.convert(
                unit_price, source_currency, target_currency
            )

            order['unit_price'] = str(converted_price)
            order['total_amount'] = str(total)
            order['currency'] = target_currency
            order['original_currency'] = source_currency
            order['exchange_rate_applied'] = 'yes'

        else:
            # Calculate total even if no conversion needed
            unit_price = Decimal(str(order['unit_price']))
            quantity = int(order['quantity'])
            total = (unit_price * quantity).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP
            )
            order['total_amount'] = str(total)

        return order

    def _check_inventory(self, order: Dict) -> bool:
        """Check and reserve inventory for order atomically."""
        product_id = order['product_id']
        quantity = int(order['quantity'])

        # Use atomic check_and_reserve to prevent race conditions
        success, actual_qty = self.inventory.check_and_reserve(
            product_id, quantity
        )

        if not success:
            error_msg = (
                f"Insufficient inventory for {product_id}: "
                f"requested {quantity}, available {actual_qty}"
            )
            self.stats['errors'].append(error_msg)
            logger.warning(error_msg)
            return False

        order['inventory_reserved'] = 'yes'
        order['fulfillment_status'] = 'ready'

        return True

    def get_summary_report(self) -> Dict:
        """Generate processing summary report."""
        return {
            'summary': {
                'total_processed': self.stats['total_orders'],
                'successful': self.stats['valid_orders'],
                'failed': self.stats['invalid_orders'],
                'duplicates_removed': self.stats['duplicates_merged'],
                'inventory_issues': self.stats['inventory_failures'],
                'success_rate': (
                    self.stats['valid_orders'] /
                    max(self.stats['total_orders'], 1) * 100
                )
            },
            'errors': self.stats['errors'][:20],  # First 20 errors
            'warnings': self.stats['warnings'][:20]
        }


def main():
    """Command-line interface for order processor."""
    import argparse

    parser = argparse.ArgumentParser(
        description='E-commerce Order Processing System'
    )
    parser.add_argument('input', help='Input CSV file or directory')
    parser.add_argument('output', help='Output CSV file or directory')
    parser.add_argument('--inventory', '-i',
                       help='Inventory CSV file (product_id, quantity)')
    parser.add_argument('--currency', '-c', default='USD',
                       help='Target currency (default: USD)')
    parser.add_argument('--batch', action='store_true',
                       help='Process all CSV files in input directory')
    parser.add_argument('--report', '-r',
                       help='Output summary report as JSON')

    args = parser.parse_args()

    # Build configuration
    config = {}
    if args.inventory:
        config['inventory_file'] = args.inventory

    processor = OrderProcessor(config)

    try:
        if args.batch and os.path.isdir(args.input):
            # Batch mode: process all CSV files in directory
            csv_files = [
                os.path.join(args.input, f)
                for f in os.listdir(args.input)
                if f.endswith('.csv')
            ]

            if not csv_files:
                print("No CSV files found in input directory")
                sys.exit(1)

            os.makedirs(args.output, exist_ok=True)
            results = processor.process_batch(csv_files, args.output,
                                             args.currency)

            print(f"\nBatch Processing Complete:")
            print(f"  Files processed: {len(results)}")

            for result in results:
                if 'error' in result:
                    print(f"  ✗ {result['input_file']}: {result['error']}")
                else:
                    print(f"  ✓ {result['input_file']}: "
                          f"{result['valid_orders']} orders")

        else:
            # Single file mode
            stats = processor.process_file(args.input, args.output,
                                          args.currency)

            print(f"\nProcessing Summary:")
            print(f"  Total orders: {stats['total_orders']}")
            print(f"  Valid orders: {stats['valid_orders']}")
            print(f"  Invalid orders: {stats['invalid_orders']}")
            print(f"  Duplicates merged: {stats['duplicates_merged']}")
            print(f"  Inventory failures: {stats['inventory_failures']}")

        # Generate report if requested
        if args.report:
            report = processor.get_summary_report()
            with open(args.report, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, default=str)
            print(f"\nReport saved to: {args.report}")

    except Exception as e:
        logger.error(f"Processing failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
