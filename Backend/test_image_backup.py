"""
Test script for Image Backup System
Run this to verify the new backup system works correctly
"""

import sys
from pathlib import Path

# Add Backend to path
sys.path.insert(0, str(Path(__file__).parent))

def test_import():
    """Test that the module can be imported"""
    try:
        from backup_image import ImageBackupManager
        print("[OK] Import successful")
        return True
    except Exception as e:
        print(f"[FAIL] Import failed: {e}")
        return False

def test_initialization():
    """Test that the manager can be initialized"""
    try:
        from backup_image import ImageBackupManager
        import json
        
        # Load config
        base_dir = Path(__file__).parent.parent
        config_file = base_dir / "Konfiguration" / "settings.json"
        if config_file.exists():
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
        else:
            config = {
                'paths': {
                    'data_base_dir': './Speicher',
                    'attachments_dir': '',
                    'backup_dir': './Backups'
                }
            }
        
        manager = ImageBackupManager(base_dir, config)
        print("[OK] Initialization successful")
        print(f"  - Backup dir: {manager.backup_dir}")
        print(f"  - Data dir: {manager.data_base_dir}")
        print(f"  - Akten dir: {manager.akten_dir}")
        return True
    except Exception as e:
        print(f"[FAIL] Initialization failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_collect_items():
    """Test that items can be collected for backup"""
    try:
        from backup_image import ImageBackupManager
        import json
        
        base_dir = Path(__file__).parent.parent
        config_file = base_dir / "Konfiguration" / "settings.json"
        if config_file.exists():
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
        else:
            config = {
                'paths': {
                    'data_base_dir': './Speicher',
                    'attachments_dir': '',
                    'backup_dir': './Backups'
                }
            }
        
        manager = ImageBackupManager(base_dir, config)
        items = manager._collect_items_to_backup()
        
        print("[OK] Item collection successful")
        print(f"  - Total items: {len(items)}")
        
        # Count by type
        by_type = {}
        for item in items:
            by_type[item['type']] = by_type.get(item['type'], 0) + 1
        
        for item_type, count in by_type.items():
            print(f"  - {item_type}: {count}")
        
        return True
    except Exception as e:
        print(f"[FAIL] Item collection failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("=" * 60)
    print("Image Backup System Test")
    print("=" * 60)
    
    tests = [
        ("Import Test", test_import),
        ("Initialization Test", test_initialization),
        ("Item Collection Test", test_collect_items),
    ]
    
    results = []
    for name, test_func in tests:
        print(f"\n{name}:")
        print("-" * 40)
        result = test_func()
        results.append((name, result))
    
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status}: {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n[OK] All tests passed! The new backup system is ready.")
        return 0
    else:
        print("\n[FAIL] Some tests failed. Please review the errors above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
