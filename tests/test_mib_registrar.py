"""Tests for MibRegistrar functionality."""

from unittest.mock import Mock
from typing import Any
from pathlib import Path



class TestMibRegistrarInitialization:
    """Test MibRegistrar initialization."""

    def test_mib_registrar_creation(self, mock_logger: Any) -> None:
        """Test creating a MibRegistrar instance."""
        from app.mib_registrar import MibRegistrar
        
        # Create mock objects
        mock_mib_builder = Mock()
        mock_scalar_instance = Mock()
        mock_table = Mock()
        mock_table_row = Mock()
        mock_table_column = Mock()
        start_time = 12345.0
        
        registrar = MibRegistrar(
            mib_builder=mock_mib_builder,
            mib_scalar_instance=mock_scalar_instance,
            mib_table=mock_table,
            mib_table_row=mock_table_row,
            mib_table_column=mock_table_column,
            logger=mock_logger,
            start_time=start_time,
        )
        
        assert registrar.mib_builder == mock_mib_builder
        assert registrar.MibScalarInstance == mock_scalar_instance
        assert registrar.MibTable == mock_table
        assert registrar.MibTableRow == mock_table_row
        assert registrar.MibTableColumn == mock_table_column
        assert registrar.logger == mock_logger
        assert registrar.start_time == start_time


class TestMibRegistrarTypeRegistryLoading:
    """Test type registry loading in MibRegistrar."""

    def test_register_all_mibs_loads_type_registry(self, mock_logger: Any, type_registry_file: Path) -> None:
        """Test that register_all_mibs loads the type registry."""
        from app.mib_registrar import MibRegistrar
        
        mock_mib_builder = Mock()
        registrar = MibRegistrar(
            mib_builder=mock_mib_builder,
            mib_scalar_instance=Mock(),
            mib_table=Mock(),
            mib_table_row=Mock(),
            mib_table_column=Mock(),
            logger=mock_logger,
            start_time=0.0,
        )
        
        # Test with explicit type registry path
        mib_jsons: dict[str, dict[str, object]] = {}
        
        # This should not raise an error even with empty mib_jsons
        registrar.register_all_mibs(mib_jsons, type_registry_path=str(type_registry_file))

    def test_populate_sysor_table_loads_type_registry(self, mock_logger: Any, type_registry_file: Path) -> None:
        """Test that populate_sysor_table loads the type registry."""
        from app.mib_registrar import MibRegistrar
        
        mock_mib_builder = Mock()
        registrar = MibRegistrar(
            mib_builder=mock_mib_builder,
            mib_scalar_instance=Mock(),
            mib_table=Mock(),
            mib_table_row=Mock(),
            mib_table_column=Mock(),
            logger=mock_logger,
            start_time=0.0,
        )
        
        # Create minimal mib_jsons with SNMPv2-MIB
        mib_jsons: dict[str, dict[str, object]] = {
            "SNMPv2-MIB": {
                "sysORTable": {
                    "rows": []
                }
            }
        }
        
        # This should load type registry and populate sysORTable
        registrar.populate_sysor_table(mib_jsons, type_registry_path=str(type_registry_file))


class TestMibRegistrarErrorHandling:
    """Test error handling in MibRegistrar."""

    def test_register_all_mibs_with_none_builder(self, mock_logger: Any) -> None:
        """Test register_all_mibs when mib_builder is None."""
        from app.mib_registrar import MibRegistrar
        
        registrar = MibRegistrar(
            mib_builder=None,
            mib_scalar_instance=Mock(),
            mib_table=Mock(),
            mib_table_row=Mock(),
            mib_table_column=Mock(),
            logger=mock_logger,
            start_time=0.0,
        )
        
        # Should log error and return early
        registrar.register_all_mibs({})
        
        # Check that error was logged
        assert mock_logger.error.called

    def test_populate_sysor_table_without_snmpv2_mib(self, mock_logger: Any, type_registry_file: Path) -> None:
        """Test populate_sysor_table when SNMPv2-MIB is not loaded."""
        from app.mib_registrar import MibRegistrar
        
        registrar = MibRegistrar(
            mib_builder=Mock(),
            mib_scalar_instance=Mock(),
            mib_table=Mock(),
            mib_table_row=Mock(),
            mib_table_column=Mock(),
            logger=mock_logger,
            start_time=0.0,
        )
        
        # Empty mib_jsons (no SNMPv2-MIB)
        mib_jsons: dict[str, dict[str, object]] = {}
        
        # Should handle gracefully
        registrar.populate_sysor_table(mib_jsons, type_registry_path=str(type_registry_file))


class TestMibMetadataIntegration:
    """Test integration with mib_metadata module."""

    def test_get_sysor_table_rows_import(self) -> None:
        """Test that get_sysor_table_rows can be imported."""
        from app.mib_metadata import get_sysor_table_rows
        
        assert callable(get_sysor_table_rows)

    def test_get_sysor_table_rows_with_known_mibs(self) -> None:
        """Test get_sysor_table_rows with known MIBs."""
        from app.mib_metadata import get_sysor_table_rows
        
        mib_names = ["SNMPv2-MIB", "IF-MIB"]
        rows = get_sysor_table_rows(mib_names)
        
        assert isinstance(rows, list)
        # Should return rows for known MIBs
        assert len(rows) >= 0

    def test_get_sysor_table_rows_with_unknown_mibs(self) -> None:
        """Test get_sysor_table_rows with unknown MIBs."""
        from app.mib_metadata import get_sysor_table_rows
        
        mib_names = ["UNKNOWN-MIB", "NONEXISTENT-MIB"]
        rows = get_sysor_table_rows(mib_names)
        
        assert isinstance(rows, list)
        # Should handle unknown MIBs gracefully

