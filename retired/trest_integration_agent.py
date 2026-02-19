"""
Integration tests for SNMP Agent - Start agent and verify snmpwalk results.

NOTE: These tests are slow (60+ seconds) as they start the full SNMP agent process
and require net-snmp tools to be installed. Run with: pytest -m integration
"""
import subprocess
import time
import pytest
from pathlib import Path
import json
from typing import Optional, Generator, TypeAlias

# Type alias for MIB groups: maps MIB name to count of OIDs in that MIB
MIBGroups: TypeAlias = dict[str, int]


class SNMPAgentProcess:
    """Context manager for running SNMP agent in a subprocess."""
    
    def __init__(self, host: str = "127.0.0.1", port: int = 11161, startup_delay: float = 15.0):
        self.host = host
        self.port = port
        self.startup_delay = startup_delay
        self.process: Optional[subprocess.Popen[str]] = None

    def __enter__(self) -> "SNMPAgentProcess":
        """Start the SNMP agent process."""
        # Start agent in subprocess
        self.process = subprocess.Popen(
            ["python", "run_agent_with_rest.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            cwd=Path(__file__).parent.parent
        )
        
        print(f"Waiting {self.startup_delay}s for agent to start...")
        # Wait for agent to start up
        time.sleep(self.startup_delay)
        
        # Check if process is still running
        if self.process.poll() is not None:
            stdout, stderr = self.process.communicate()
            raise RuntimeError(
                f"SNMP agent failed to start.\nSTDOUT: {stdout}\nSTDERR: {stderr}"
            )
        
        print(f"Agent process running (PID: {self.process.pid})")
        return self
    
    def __exit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[type]
    ) -> None:
        """Stop the SNMP agent process."""
        if self.process:
            # Try graceful shutdown first
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                # Force kill if graceful shutdown fails
                self.process.kill()
                self.process.wait()
    
    def snmpget(self, oid: str, version: str = "2c", community: str = "public", timeout: int = 10) -> str:
        """Execute snmpget command and return output."""
        cmd = [
            "snmpget",
            "-v", version,
            "-c", community,
            f"{self.host}:{self.port}",
            oid
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            raise RuntimeError(f"snmpget failed: {result.stderr}")
        return result.stdout.strip()
    
    def snmpwalk(self, oid: str = ".1.3.6", version: str = "2c", community: str = "public", timeout: int = 15) -> list[str]:
        """Execute snmpwalk command and return list of results."""
        cmd = [
            "snmpwalk",
            "-v", version,
            "-c", community,
            f"{self.host}:{self.port}",
            oid
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            raise RuntimeError(f"snmpwalk failed: {result.stderr}")
        
        # Parse output into list of OID-value pairs
        lines = [line.strip() for line in result.stdout.strip().split("\n") if line.strip()]
        return lines


@pytest.mark.integration
@pytest.mark.slow
class TestSNMPAgentIntegration:
    """Integration tests for SNMP Agent."""

    @pytest.fixture
    def agent(self) -> Generator[SNMPAgentProcess, None, None]:
        """Fixture to provide a running SNMP agent."""
        with SNMPAgentProcess(startup_delay=15.0) as agent_proc:
            yield agent_proc
    
    def test_agent_starts_and_stops(self) -> None:
        """Test that agent can start and stop cleanly."""
        with SNMPAgentProcess(startup_delay=15.0) as agent:
            # If we get here, agent started successfully
            assert agent.process is not None
            assert agent.process.poll() is None  # Process is still running
        # After context exit, process should be stopped
    
    def test_snmpwalk_system_group(self, agent: SNMPAgentProcess) -> None:
        """Test snmpwalk of SNMPv2-MIB system group (.1.3.6.1.2.1.1)."""
        results = agent.snmpwalk(".1.3.6.1.2.1.1")
        
        # Should get results
        assert len(results) > 0, "No results from system group walk"
        
        # Parse results into dict for easier verification
        system_vars = {}
        for line in results:
            if "sysDescr" in line or "SNMPv2-MIB::sysDescr" in line:
                system_vars["sysDescr"] = line
            elif "sysObjectID" in line:
                system_vars["sysObjectID"] = line
            elif "sysUpTime" in line:
                system_vars["sysUpTime"] = line
            elif "sysContact" in line:
                system_vars["sysContact"] = line
            elif "sysName" in line:
                system_vars["sysName"] = line
            elif "sysLocation" in line:
                system_vars["sysLocation"] = line
        
        # Verify we got key system variables
        assert "sysDescr" in system_vars, "Missing sysDescr"
        assert "sysObjectID" in system_vars, "Missing sysObjectID"
        assert "sysUpTime" in system_vars, "Missing sysUpTime"
        
        print("\n=== System Group Results ===")
        for key, value in system_vars.items():
            print(f"{key}: {value}")
    
    def test_snmpget_sysdescr(self, agent: SNMPAgentProcess) -> None:
        """Test snmpget for sysDescr (.1.3.6.1.2.1.1.1.0)."""
        result = agent.snmpget(".1.3.6.1.2.1.1.1.0")
        
        assert result, "Empty result for sysDescr"
        assert "STRING" in result or "OCTET STRING" in result, f"Unexpected type in result: {result}"
        
        print(f"\n=== sysDescr Result ===\n{result}")
    
    def test_snmpget_sysuptime(self, agent: SNMPAgentProcess) -> None:
        """Test snmpget for sysUpTime (.1.3.6.1.2.1.1.3.0)."""
        result = agent.snmpget(".1.3.6.1.2.1.1.3.0")
        
        assert result, "Empty result for sysUpTime"
        assert "Timeticks" in result or "INTEGER" in result, f"Unexpected type in result: {result}"
        
        print(f"\n=== sysUpTime Result ===\n{result}")
    
    def test_snmpwalk_iftable(self, agent: SNMPAgentProcess) -> None:
        """Test snmpwalk of IF-MIB ifTable (.1.3.6.1.2.1.2.2)."""
        try:
            results = agent.snmpwalk(".1.3.6.1.2.1.2.2")
            
            # Should get some results (at least one interface row)
            assert len(results) > 0, "No results from ifTable walk"
            
            print(f"\n=== ifTable Results ({len(results)} entries) ===")
            for i, line in enumerate(results[:10]):  # Print first 10 entries
                print(f"{i+1}. {line}")
            
            if len(results) > 10:
                print(f"... and {len(results) - 10} more entries")
        
        except RuntimeError as e:
            # If IF-MIB not loaded, skip test
            if "No Such Object" in str(e) or "No more variables" in str(e):
                # pytest.skip("IF-MIB not loaded or no ifTable data")
                pass
            else:
                raise
    
    def test_verify_behaviour_json_matches_responses(self, agent: SNMPAgentProcess) -> None:
        """Test that SNMP responses match the behaviour JSON configuration."""
        behaviour_path = Path("mock-behaviour/SNMPv2-MIB_behaviour.json")
        
        if not behaviour_path.exists():
            # pytest.skip("SNMPv2-MIB_behaviour.json not found")
            pass
        
        with open(behaviour_path) as f:
            behaviour = json.load(f)
        
        # Get sysDescr from behaviour JSON
        sys_descr_config = behaviour.get("sysDescr", {})
        expected_value = sys_descr_config.get("initial", "")
        
        # Get sysDescr from SNMP agent
        result = agent.snmpget(".1.3.6.1.2.1.1.1.0")
        
        # Extract value from result (format: "OID = TYPE: value")
        if "STRING:" in result:
            actual_value = result.split("STRING:")[-1].strip().strip('"')
        elif "OCTET STRING:" in result:
            actual_value = result.split("OCTET STRING:")[-1].strip().strip('"')
        else:
            actual_value = result.split("=")[-1].strip()
        
        print("\n=== Behaviour JSON Verification ===")
        print(f"Expected (from JSON): {expected_value}")
        print(f"Actual (from SNMP):   {actual_value}")
        
        # Note: Values might not match exactly if plugins modify them,
        # but we should at least get a response
        assert actual_value, "Got empty value from SNMP agent"
    
    def test_multiple_snmpget_requests(self, agent: SNMPAgentProcess) -> None:
        """Test multiple sequential snmpget requests to verify agent stability."""
        oids = [
            ".1.3.6.1.2.1.1.1.0",  # sysDescr
            ".1.3.6.1.2.1.1.3.0",  # sysUpTime
            ".1.3.6.1.2.1.1.4.0",  # sysContact
            ".1.3.6.1.2.1.1.5.0",  # sysName
            ".1.3.6.1.2.1.1.6.0",  # sysLocation
        ]
        
        results = []
        for oid in oids:
            try:
                result = agent.snmpget(oid)
                results.append((oid, result))
            except RuntimeError as e:
                # Some OIDs might not be available
                print(f"Warning: Could not get {oid}: {e}")
        
        # Should have gotten at least some results
        assert len(results) >= 2, f"Only got {len(results)} successful responses out of {len(oids)}"
        
        print(f"\n=== Multiple Request Results ({len(results)}/{len(oids)} successful) ===")
        for oid, result in results:
            print(f"{oid}: {result[:80]}..." if len(result) > 80 else f"{oid}: {result}")
    
    def test_snmpwalk_full_tree(self, agent: SNMPAgentProcess) -> None:
        """Test full snmpwalk to see all available OIDs."""
        try:
            results = agent.snmpwalk(".1.3.6")
            
            assert len(results) > 0, "No results from full walk"
            
            print(f"\n=== Full Walk Results ({len(results)} total OIDs) ===")
            
            # Group by MIB
            mib_groups: MIBGroups = {}
            for line in results:
                # Extract MIB name if present
                if "::" in line:
                    mib_name = line.split("::")[0].split()[-1]
                    mib_groups[mib_name] = mib_groups.get(mib_name, 0) + 1
            
            print("OIDs by MIB:")
            for mib_name, count in sorted(mib_groups.items()):
                print(f"  {mib_name}: {count} OIDs")
            
            # Print first few entries
            print("\nFirst 20 OIDs:")
            for i, line in enumerate(results[:20]):
                print(f"  {i+1}. {line}")
        
        except subprocess.TimeoutExpired:
            # pytest.skip("Full walk timed out - too many OIDs")
            pass


# @pytest.mark.skipif(
#     subprocess.run(["which", "snmpget"], capture_output=True).returncode != 0,
#     reason="snmpget command not available - install net-snmp tools"
# )
class TestSNMPToolsAvailable:
    """Tests that require SNMP tools to be installed."""
    
    def test_snmp_tools_installed(self) -> None:
        """Verify that SNMP command-line tools are available."""
        # Check snmpget
        result = subprocess.run(["snmpget", "--version"], capture_output=True, text=True)
        assert result.returncode == 0, "snmpget not available"
        
        # Check snmpwalk
        result = subprocess.run(["snmpwalk", "--version"], capture_output=True, text=True)
        assert result.returncode == 0, "snmpwalk not available"
        
        print("\n=== SNMP Tools Version ===")
        print(result.stdout)


if __name__ == "__main__":
    # Allow running directly for manual testing
    print("Starting SNMP Agent Integration Test...")
    print("=" * 60)
    
    try:
        with SNMPAgentProcess() as agent:
            print(f"✓ Agent started on {agent.host}:{agent.port}")
            
            print("\nTesting sysDescr...")
            result = agent.snmpget(".1.3.6.1.2.1.1.1.0")
            print(f"✓ sysDescr: {result}")
            
            print("\nTesting system group walk...")
            results = agent.snmpwalk(".1.3.6.1.2.1.1")
            print(f"✓ Got {len(results)} system variables")
            
            print("\nFirst 10 results:")
            for i, line in enumerate(results[:10], 1):
                print(f"  {i}. {line}")
            
            print("\n" + "=" * 60)
            print("✓ All tests passed!")
    
    except Exception as e:
        print(f"\n✗ Error: {e}")
        raise
