import os
import json
import hashlib
import functools
import logging
import threading
import inspect
import time
import asyncio
from pathlib import Path
from typing import Callable
from rxconfig import isProd

def dev_cache(
    func: Callable = None,
    *,
    cache_args: list[str] = None,
    cache_delay_seconds: float = 0.0,
) -> Callable:
    """
    Development-mode caching decorator that records/replays function calls.

    Args:
        cache_args: List of argument names to include in cache key generation.
                   If None, all arguments are used (default behavior).
        cache_delay_seconds: Optional. Sleep this duration (in seconds) before returning result
                   when serving cached results in development mode. Default: 0.0 (no delay).

    Behavior controlled by SQLLM_DEV_CACHE_SETTING environment variable:
    - 'RECORD': Passively records inputs and outputs (default in dev mode)
    - 'USE_CACHE': Uses cache when available, falls back to calling function
    - 'USE_CACHE_ONLY': Strict cache-only mode, errors on cache miss

    In production mode (isProd() == True), this is a transparent wrapper.

    Cache structure: .cache/sqllm_dev_cache.json
    {
        "module.name": {
            "function_name": {
                "arg_hash": serialized_result
            }
        }
    }
    """

    def decorator(func: Callable) -> Callable:
        # In production, return transparent wrapper
        if isProd():
            return func

        # Get cache mode from environment variable
        mode = os.getenv("SQLLM_DEV_CACHE_SETTING", "").upper()
        valid_modes = {"RECORD", "USE_CACHE", "USE_CACHE_ONLY"}

        # Validate and default to RECORD if invalid
        if mode not in valid_modes:
            if mode:  # Non-empty but invalid
                logging.warning(
                    f"Invalid SQLLM_DEV_CACHE_SETTING value: '{mode}'. "
                    f"Valid options: {', '.join(valid_modes)}. Defaulting to 'RECORD'."
                )
            else:  # Empty/unset
                logging.info(
                    "SQLLM_DEV_CACHE_SETTING not set. Defaulting to 'RECORD' mode."
                )
            mode = "RECORD"

        # Setup cache file
        cache_dir = Path(".cache")
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = cache_dir / "sqllm_dev_cache.json"

        # Thread lock for cache operations
        cache_lock = threading.Lock()

        # Load existing cache
        cache_data = {}
        if cache_file.exists():
            try:
                with open(cache_file, "r") as f:
                    cache_data = json.load(f)
            except Exception as e:
                logging.warning(f"Failed to load cache file {cache_file}: {e}")
                cache_data = {}

        # Get module and function keys
        module_key = func.__module__
        function_key = func.__qualname__

        # Initialize cache structure for this function
        if module_key not in cache_data:
            cache_data[module_key] = {}
        if function_key not in cache_data[module_key]:
            cache_data[module_key][function_key] = {}

        # Get function signature for argument filtering
        sig = inspect.signature(func)
        param_names = list(sig.parameters.keys())

        # Determine which args to include in cache key
        if cache_args is not None:
            included = set(cache_args)
            # Validate that specified args exist in function signature
            invalid_args = included - set(param_names)
            if invalid_args:
                logging.warning(
                    f"cache_args contains invalid parameter names for {func.__name__}: {invalid_args}"
                )
        else:
            # If not specified, use all args (default behavior)
            included = set(param_names)

        def _save_cache():
            """Save cache to disk atomically (must be called with lock held)."""
            try:
                temp_file = cache_file.with_suffix(".json.tmp")
                with open(temp_file, "w") as f:
                    json.dump(cache_data, f, indent=2, default=str)
                temp_file.replace(cache_file)
            except Exception as e:
                logging.error(f"Failed to save cache to {cache_file}: {e}")

        def _make_cache_key(args: tuple, kwargs: dict) -> str:
            """Generate a unique cache key from specified function arguments."""
            # Build a dict mapping param names to values (only for included args)
            bound_args = {}
            for i, param_name in enumerate(param_names):
                if param_name in included and i < len(args):
                    bound_args[param_name] = args[i]

            # Add kwargs that are included
            for key, value in kwargs.items():
                if key in included:
                    bound_args[key] = value

            # Serialize to JSON for stable hashing
            try:
                key_str = json.dumps(bound_args, sort_keys=True, default=str)
            except (TypeError, ValueError):
                # Fallback to string representation if JSON fails
                key_str = str(sorted(bound_args.items()))

            # Use hash for compact keys
            return hashlib.sha256(key_str.encode()).hexdigest()

        # Check if function is async
        if inspect.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                cache_key = _make_cache_key(args, kwargs)

                if mode == "RECORD":
                    # Always call function and record result
                    result = await func(*args, **kwargs)
                    with cache_lock:
                        function_cache = cache_data[module_key][function_key]
                        function_cache[cache_key] = result
                        _save_cache()
                    logging.debug(f"[RECORD] Cached result for {module_key}.{function_key}")
                    return result

                elif mode == "USE_CACHE":
                    # Try cache first, fallback to calling function
                    cache_hit = False
                    result = None
                    with cache_lock:
                        function_cache = cache_data[module_key][function_key]
                        if cache_key in function_cache:
                            cache_hit = True
                            result = function_cache[cache_key]
                            logging.debug(
                                f"[USE_CACHE] Cache hit for {module_key}.{function_key}"
                            )
                    if cache_hit:
                        if cache_delay_seconds > 0:
                            await asyncio.sleep(cache_delay_seconds)
                        return result

                    # Cache miss - call function outside lock
                    logging.debug(
                        f"[USE_CACHE] Cache miss for {module_key}.{function_key}, calling function"
                    )
                    result = await func(*args, **kwargs)

                    # Store result with lock
                    with cache_lock:
                        function_cache = cache_data[module_key][function_key]
                        function_cache[cache_key] = result
                        _save_cache()
                    return result

                elif mode == "USE_CACHE_ONLY":
                    # Strict cache-only mode, error on miss
                    cache_hit = False
                    result = None
                    with cache_lock:
                        function_cache = cache_data[module_key][function_key]
                        if cache_key in function_cache:
                            cache_hit = True
                            result = function_cache[cache_key]
                            logging.debug(
                                f"[USE_CACHE_ONLY] Cache hit for {module_key}.{function_key}"
                            )
                    if cache_hit:
                        if cache_delay_seconds > 0:
                            await asyncio.sleep(cache_delay_seconds)
                        return result

                    raise RuntimeError(
                        f"Cache miss in USE_CACHE_ONLY mode for {module_key}.{function_key}. "
                        f"No cached result found for arguments hash: {cache_key[:16]}..."
                    )

                # Fallback (should never reach here)
                return await func(*args, **kwargs)

            return async_wrapper
        else:
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                cache_key = _make_cache_key(args, kwargs)

                if mode == "RECORD":
                    # Always call function and record result
                    result = func(*args, **kwargs)
                    with cache_lock:
                        function_cache = cache_data[module_key][function_key]
                        function_cache[cache_key] = result
                        _save_cache()
                    logging.debug(f"[RECORD] Cached result for {module_key}.{function_key}")
                    return result

                elif mode == "USE_CACHE":
                    # Try cache first, fallback to calling function
                    cache_hit = False
                    result = None
                    with cache_lock:
                        function_cache = cache_data[module_key][function_key]
                        if cache_key in function_cache:
                            cache_hit = True
                            result = function_cache[cache_key]
                            logging.debug(
                                f"[USE_CACHE] Cache hit for {module_key}.{function_key}"
                            )
                    if cache_hit:
                        if cache_delay_seconds > 0:
                            time.sleep(cache_delay_seconds)
                        return result

                    # Cache miss - call function outside lock
                    logging.debug(
                        f"[USE_CACHE] Cache miss for {module_key}.{function_key}, calling function"
                    )
                    result = func(*args, **kwargs)

                    # Store result with lock
                    with cache_lock:
                        function_cache = cache_data[module_key][function_key]
                        function_cache[cache_key] = result
                        _save_cache()
                    return result

                elif mode == "USE_CACHE_ONLY":
                    # Strict cache-only mode, error on miss
                    cache_hit = False
                    result = None
                    with cache_lock:
                        function_cache = cache_data[module_key][function_key]
                        if cache_key in function_cache:
                            cache_hit = True
                            result = function_cache[cache_key]
                            logging.debug(
                                f"[USE_CACHE_ONLY] Cache hit for {module_key}.{function_key}"
                            )
                    if cache_hit:
                        if cache_delay_seconds > 0:
                            time.sleep(cache_delay_seconds)
                        return result

                    raise RuntimeError(
                        f"Cache miss in USE_CACHE_ONLY mode for {module_key}.{function_key}. "
                        f"No cached result found for arguments hash: {cache_key[:16]}..."
                    )

                # Fallback (should never reach here)
                return func(*args, **kwargs)

            return wrapper

    # Support both @dev_cache and @dev_cache(cache_args=[...])
    if func is None:
        return decorator
    else:
        return decorator(func)
