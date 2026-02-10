#!/usr/bin/env python3
"""
Tests for P0 reliability features:
- Atomic file writes
- State backups
- Provider health checks
- Crash recovery
"""

import os
import sys
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, patch

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bardacle import (
    write_atomic,
    write_atomic_json,
    backup_state,
    prune_backups,
    list_backups,
    recover_from_backup,
    get_backup_dir,
    save_emergency_state,
    check_emergency_state,
    ProviderHealth,
    CONFIG,
    LAST_KNOWN_STATE,
    LAST_STATE_METADATA
)


class TestAtomicWrites:
    """Test atomic file write operations."""
    
    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.test_file = Path(self.temp_dir) / "test.txt"
    
    def teardown_method(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_atomic_write_creates_file(self):
        """Test that atomic write creates the file."""
        content = "Hello, World!"
        result = write_atomic(content, self.test_file)
        
        assert result is True
        assert self.test_file.exists()
        assert self.test_file.read_text() == content
    
    def test_atomic_write_no_temp_file_left(self):
        """Test that no .tmp file is left after successful write."""
        content = "Test content"
        write_atomic(content, self.test_file)
        
        temp_file = self.test_file.with_suffix('.tmp')
        assert not temp_file.exists()
    
    def test_atomic_write_creates_parent_dirs(self):
        """Test that parent directories are created."""
        deep_file = Path(self.temp_dir) / "a" / "b" / "c" / "test.txt"
        result = write_atomic("content", deep_file)
        
        assert result is True
        assert deep_file.exists()
    
    def test_atomic_json_write(self):
        """Test atomic JSON write."""
        data = {"key": "value", "number": 42}
        json_file = Path(self.temp_dir) / "test.json"
        
        result = write_atomic_json(data, json_file)
        
        assert result is True
        assert json_file.exists()
        
        import json
        loaded = json.loads(json_file.read_text())
        assert loaded == data


class TestBackups:
    """Test backup functionality."""
    
    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.state_file = Path(self.temp_dir) / "state.md"
        self.backup_dir = Path(self.temp_dir) / "session-history"
        
        # Write initial state
        self.state_file.write_text("# Initial State\nSome content")
    
    def teardown_method(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_backup_creates_file(self):
        """Test that backup creates a file."""
        # Mock get_backup_dir to return our temp directory
        with patch('bardacle.get_backup_dir', return_value=self.backup_dir):
            with patch('bardacle.CONFIG') as mock_config:
                mock_config.output.backup_count = 5
                backup_path = backup_state(self.state_file)
        
        assert backup_path is not None
        assert backup_path.exists()
        assert self.backup_dir.exists()
    
    def test_backup_content_matches(self):
        """Test that backup content matches original."""
        with patch('bardacle.get_backup_dir', return_value=self.backup_dir):
            with patch('bardacle.CONFIG') as mock_config:
                mock_config.output.backup_count = 5
                backup_path = backup_state(self.state_file)
        
        original = self.state_file.read_text()
        backed_up = backup_path.read_text()
        assert original == backed_up
    
    def test_prune_keeps_max_backups(self):
        """Test that pruning keeps only max_count backups."""
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        # Create 10 backup files
        for i in range(10):
            backup = self.backup_dir / f"state-2026020{i}-120000.md"
            backup.write_text(f"backup {i}")
        
        prune_backups(self.backup_dir, "state", max_count=5)
        
        remaining = list(self.backup_dir.glob("state-*.md"))
        assert len(remaining) == 5


class TestProviderHealth:
    """Test provider health checking."""
    
    def setup_method(self):
        self.health = ProviderHealth()
    
    def test_initial_state(self):
        """Test that providers start with no status."""
        assert len(self.health.status) == 0
    
    def test_mark_success(self):
        """Test marking a provider as successful."""
        self.health.mark_success("local")
        
        status = self.health.status["local"]
        assert status["available"] is True
        assert status["failures"] == 0
    
    def test_mark_failed(self):
        """Test marking a provider as failed."""
        self.health.mark_failed("groq")
        
        status = self.health.status["groq"]
        assert status["available"] is False
        assert status["failures"] == 1
    
    def test_failure_accumulation(self):
        """Test that failures accumulate."""
        for _ in range(5):
            self.health.mark_failed("openai")
        
        status = self.health.status["openai"]
        assert status["failures"] == 5
    
    def test_success_resets_failures(self):
        """Test that success resets failure count."""
        for _ in range(5):
            self.health.mark_failed("local")
        
        self.health.mark_success("local")
        
        status = self.health.status["local"]
        assert status["failures"] == 0
        assert status["available"] is True


class TestCrashRecovery:
    """Test crash recovery functionality."""
    
    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
    
    def teardown_method(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_emergency_state_detection(self):
        """Test detection of emergency state file."""
        # Create emergency state
        emergency_dir = Path(self.temp_dir)
        emergency_file = emergency_dir / "emergency-state.md"
        emergency_file.write_text("# Emergency\nCrash state")
        
        with patch('bardacle.CONFIG') as mock_config:
            mock_config.output.state_file = str(emergency_dir / "state.md")
            result = check_emergency_state()
        
        assert result == emergency_file
    
    def test_no_emergency_state(self):
        """Test when no emergency state exists."""
        with patch('bardacle.CONFIG') as mock_config:
            mock_config.output.state_file = str(Path(self.temp_dir) / "state.md")
            result = check_emergency_state()
        
        assert result is None


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
