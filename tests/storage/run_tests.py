#!/usr/bin/env python3
"""Simple test runner for storage backend validation."""

import sys
import subprocess
from pathlib import Path
from typing import List, Tuple, Dict


def detect_available_backends() -> Dict[str, List[str]]:
    """Detect which storage backends are available."""
    backends = {
        "vector": [],
        "graph": [],
        "kv": []
    }

    # Check vector storages
    try:
        import nano_vectordb
        backends["vector"].append("nano")
    except ImportError:
        pass

    try:
        import hnswlib
        backends["vector"].append("hnswlib")
    except ImportError:
        pass

    try:
        import qdrant_client
        backends["vector"].append("qdrant")
    except ImportError:
        pass

    # Check graph storages
    backends["graph"].append("networkx")  # Always available

    try:
        import neo4j
        backends["graph"].append("neo4j")
    except ImportError:
        pass

    # KV storage
    backends["kv"].append("json")  # Always available

    return backends


def run_test_suite(test_file: str, backend: str = None) -> bool:
    """Run a specific test suite."""
    print(f"\n{'='*60}")
    print(f"Running: {test_file}")
    if backend:
        print(f"Backend: {backend}")
    print('='*60)

    cmd = ["python", "-m", "pytest", test_file, "-xvs"]

    if backend:
        cmd.extend(["--backend", backend])

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode == 0:
        print("✅ PASSED")
        return True
    else:
        print("❌ FAILED")
        if result.stdout:
            print("Output:", result.stdout[-500:])  # Last 500 chars
        if result.stderr:
            print("Errors:", result.stderr[-500:])
        return False


def run_contract_tests() -> Dict[str, List[Tuple[str, bool]]]:
    """Run contract tests for all available backends."""
    backends = detect_available_backends()
    results = {
        "vector": [],
        "graph": [],
        "kv": []
    }

    print("\n" + "="*60)
    print("DETECTED BACKENDS")
    print("="*60)
    for storage_type, backend_list in backends.items():
        print(f"{storage_type.upper()}: {', '.join(backend_list) if backend_list else 'none'}")

    # Run existing storage tests
    print("\n" + "="*60)
    print("RUNNING STORAGE TESTS")
    print("="*60)

    test_files = {
        "vector": {
            "nano": "tests/test_hnsw_vector_storage.py",  # Note: HNSW test, not nano
            "hnswlib": "tests/test_hnsw_vector_storage.py",
            "qdrant": "tests/storage/test_qdrant_storage.py"
        },
        "graph": {
            "networkx": "tests/test_networkx_storage.py",
            "neo4j": "tests/test_neo4j_storage.py"
        },
        "kv": {
            "json": None  # No specific test yet
        }
    }

    for storage_type, backend_list in backends.items():
        for backend in backend_list:
            test_file = test_files.get(storage_type, {}).get(backend)

            if test_file and Path(test_file).exists():
                success = run_test_suite(test_file)
                results[storage_type].append((backend, success))
            else:
                print(f"\nNo test file for {backend} {storage_type} storage")

    # Run integration tests if services available
    print("\n" + "="*60)
    print("RUNNING INTEGRATION TESTS")
    print("="*60)

    if "neo4j" in backends["graph"]:
        success = run_test_suite("tests/storage/integration/test_neo4j_integration.py")
        results["graph"].append(("neo4j_integration", success))

    if "qdrant" in backends["vector"]:
        success = run_test_suite("tests/storage/integration/test_qdrant_integration.py")
        results["vector"].append(("qdrant_integration", success))

    return results


def run_example_tests() -> bool:
    """Run example validation tests."""
    print("\n" + "="*60)
    print("VALIDATING EXAMPLES")
    print("="*60)

    return run_test_suite("tests/test_examples.py")


def print_summary(results: Dict[str, List[Tuple[str, bool]]], examples_passed: bool):
    """Print test summary."""
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)

    total_passed = 0
    total_failed = 0

    for storage_type, test_results in results.items():
        if test_results:
            print(f"\n{storage_type.upper()} Storage:")
            for backend, passed in test_results:
                status = "✅ PASSED" if passed else "❌ FAILED"
                print(f"  {backend}: {status}")
                if passed:
                    total_passed += 1
                else:
                    total_failed += 1

    print(f"\nExamples: {'✅ PASSED' if examples_passed else '❌ FAILED'}")
    if examples_passed:
        total_passed += 1
    else:
        total_failed += 1

    print(f"\n{'='*60}")
    print(f"Total: {total_passed} passed, {total_failed} failed")

    if total_failed == 0:
        print("🎉 All tests passed!")
    else:
        print(f"⚠️  {total_failed} test(s) failed")

    return total_failed == 0


def main():
    """Main test runner."""
    print("="*60)
    print("NANO-GRAPHRAG STORAGE TEST RUNNER")
    print("="*60)

    # Run contract tests for all backends
    results = run_contract_tests()

    # Run example validation
    examples_passed = run_example_tests()

    # Print summary
    all_passed = print_summary(results, examples_passed)

    # Exit with appropriate code
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()