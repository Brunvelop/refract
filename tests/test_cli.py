"""
Tests for refract.cli module.

All tests operate through Refract instances — there is no global ``app``
object or auto-initialization in the refract package.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from click.testing import CliRunner
import click

from refract.cli import (
    _add_command_options,
    _create_handler,
    TYPE_MAP,
)
from refract.models import ParamSchema, FunctionInfo, GenericOutput


# ============================================================================
# TYPE MAPPING AND UTILITY HELPERS
# ============================================================================

class TestTypeMappingAndUtils:
    """Tests for CLI utility functions and type mapping."""

    def test_type_map_completeness(self):
        """TYPE_MAP covers expected Python → Click type mappings."""
        expected = {
            int: click.INT,
            float: click.FLOAT,
            bool: click.BOOL,
            str: click.STRING,
        }
        for python_type, click_type in expected.items():
            assert TYPE_MAP[python_type] == click_type

    def test_add_command_options_basic(self):
        """Basic Click options are added to a command function."""
        def test_command(**kwargs):
            pass

        params = [
            ParamSchema(name="count", type=int, default=1, required=False, description="Number of items"),
            ParamSchema(name="name", type=str, required=True, description="Name parameter"),
        ]

        decorated_func = _add_command_options(test_command, params)
        command = click.command()(decorated_func)

        runner = CliRunner()
        result = runner.invoke(command, ["--help"])
        assert "--count" in result.output
        assert "--name" in result.output
        assert "Number of items" in result.output
        assert "Name parameter" in result.output

    def test_add_command_options_with_required(self):
        """Required option is enforced by Click."""
        def test_command(**kwargs):
            pass

        params = [
            ParamSchema(name="required_param", type=str, required=True, description="Required parameter"),
        ]

        decorated_func = _add_command_options(test_command, params)
        command = click.command()(decorated_func)

        runner = CliRunner()
        result = runner.invoke(command, [])
        assert result.exit_code != 0

        result = runner.invoke(command, ["--required-param", "value"])
        assert result.exit_code == 0

    def test_add_command_options_type_mapping(self):
        """Different parameter types map to correct Click options."""
        def test_command(**kwargs):
            pass

        params = [
            ParamSchema(name="int_param", type=int, default=42, required=False, description="Integer param"),
            ParamSchema(name="float_param", type=float, default=3.14, required=False, description="Float param"),
            ParamSchema(name="bool_param", type=bool, default=True, required=False, description="Boolean param"),
        ]

        decorated_func = _add_command_options(test_command, params)
        command = click.command()(decorated_func)

        runner = CliRunner()
        result = runner.invoke(command, ["--help"])
        assert "--int-param" in result.output
        assert "--float-param" in result.output
        assert "--bool-param" in result.output


# ============================================================================
# HANDLER CREATION
# ============================================================================

class TestCreateHandler:
    """Tests for _create_handler — CLI command handler creation."""

    def test_create_handler_basic(self, sample_function_info):
        """Basic command handler is callable with correct attributes."""
        handler = _create_handler("test_add", sample_function_info)
        assert callable(handler)
        assert handler.__name__ == "test_add_command"
        assert handler.__doc__ == sample_function_info.description

    def test_create_handler_execution_success(self, sample_function_info):
        """Handler executes the underlying function and echoes the result."""
        handler = _create_handler("test_add", sample_function_info)

        with patch("click.echo") as mock_echo:
            handler(x=5, y=3)
            mock_echo.assert_called_once()
            call_args = mock_echo.call_args[0][0]
            assert isinstance(call_args, GenericOutput)
            assert call_args.result == 8
            assert call_args.success is True

    def test_create_handler_execution_with_defaults(self, sample_function_info):
        """Handler uses default parameter values when argument is None."""
        handler = _create_handler("test_add", sample_function_info)

        with patch("click.echo") as mock_echo:
            handler(x=10, y=None)
            mock_echo.assert_called_once()
            call_args = mock_echo.call_args[0][0]
            assert isinstance(call_args, GenericOutput)
            assert call_args.result == 11  # 10 + default 1

    def test_create_handler_execution_error(self, sample_function_info):
        """Handler echoes error and raises Abort when function fails."""
        def error_func(x: int, y: int = 1) -> GenericOutput:
            raise ValueError("Test error")

        func_info = FunctionInfo(
            name="error_func",
            func=error_func,
            description="Error function",
            params=sample_function_info.params,
            return_type=GenericOutput,
        )

        handler = _create_handler("error_func", func_info)

        with patch("click.echo") as mock_echo, pytest.raises(click.Abort):
            handler(x=5, y=3)
            mock_echo.assert_called_with("Error executing error_func: Test error", err=True)


# ============================================================================
# EDGE CASES — COMMAND REGISTRATION
# ============================================================================

class TestCLICommandRegistrationEdgeCases:
    """Tests for edge cases in command registration."""

    def test_command_with_underscores_to_hyphens(self):
        """Parameter names with underscores become hyphenated CLI options."""
        def func_with_underscore(param_name: str) -> str:
            return param_name

        func_info = FunctionInfo(
            name="underscore_func",
            func=func_with_underscore,
            description="Function with underscore param",
            params=[
                ParamSchema(name="param_name", type=str, required=True, description="Param with underscore")
            ],
            return_type=GenericOutput,
        )

        def test_command(**kwargs):
            pass

        decorated_func = _add_command_options(test_command, func_info.params)
        command = click.command()(decorated_func)

        runner = CliRunner()
        result = runner.invoke(command, ["--help"])
        assert "--param-name" in result.output

    def test_command_with_complex_parameter_types(self):
        """Commands with various parameter types and defaults display correctly."""
        params = [
            ParamSchema(name="string_param", type=str, required=True, description="String parameter"),
            ParamSchema(name="optional_int", type=int, default=42, required=False, description="Optional integer"),
            ParamSchema(name="boolean_flag", type=bool, default=False, required=False, description="Boolean flag"),
        ]

        def complex_command(**kwargs):
            pass

        decorated_func = _add_command_options(complex_command, params)
        command = click.command()(decorated_func)

        runner = CliRunner()
        result = runner.invoke(command, ["--help"])

        assert "--string-param" in result.output
        assert "--optional-int" in result.output
        assert "--boolean-flag" in result.output
        assert "String parameter" in result.output
        assert "Optional integer" in result.output
        assert "Boolean flag" in result.output


# ============================================================================
# REFRACT INSTANCE CLI
# ============================================================================

class TestRefractCli:
    """Tests for Refract.cli(), @refract.command(), and run_cli property."""

    def _make_refract_with_function(self, sample_function_info):
        """Helper: build a Refract instance with one pre-loaded function."""
        from refract import Refract
        r = Refract("test-project")
        r._registry.append(sample_function_info)
        return r

    # ------------------------------------------------------------------
    # Basic structure
    # ------------------------------------------------------------------

    def test_cli_returns_click_group(self, sample_function_info):
        """Refract.cli() returns a Click Group."""
        from refract import Refract
        r = Refract("test-project")
        group = r.cli()
        assert isinstance(group, click.Group)

    def test_cli_has_standard_commands(self):
        """Click group includes list, serve, serve-api, serve-mcp."""
        from refract import Refract
        r = Refract("test-project")
        group = r.cli()
        assert "list" in group.commands
        assert "serve" in group.commands
        assert "serve-api" in group.commands
        assert "serve-mcp" in group.commands

    def test_cli_group_name_in_help(self):
        """The CLI group help text includes the instance name."""
        from refract import Refract
        r = Refract("my-special-project")
        group = r.cli()
        runner = CliRunner()
        result = runner.invoke(group, ["--help"])
        assert result.exit_code == 0
        assert "my-special-project" in result.output

    def test_cli_has_verbose_flag(self):
        """The Click group exposes --verbose / -v flag."""
        from refract import Refract
        r = Refract("test-project")
        group = r.cli()
        runner = CliRunner()
        result = runner.invoke(group, ["--help"])
        assert result.exit_code == 0
        assert "--verbose" in result.output or "-v" in result.output

    # ------------------------------------------------------------------
    # list command
    # ------------------------------------------------------------------

    def test_cli_list_shows_registered_functions(self, sample_function_info):
        """list command shows functions from the Refract instance's registry."""
        r = self._make_refract_with_function(sample_function_info)
        group = r.cli()
        runner = CliRunner()
        result = runner.invoke(group, ["list"])
        assert result.exit_code == 0
        assert "Available functions:" in result.output
        assert "test_add" in result.output
        assert "Add two numbers together" in result.output

    def test_cli_list_empty_registry(self):
        """list command with empty registry shows header but no functions."""
        from refract import Refract
        r = Refract("test-project")
        group = r.cli()
        runner = CliRunner()
        result = runner.invoke(group, ["list"])
        assert result.exit_code == 0
        assert "Available functions:" in result.output

    def test_cli_list_shows_parameters(self, sample_function_info):
        """list command shows parameter information for registered functions."""
        r = self._make_refract_with_function(sample_function_info)
        group = r.cli()
        runner = CliRunner()
        result = runner.invoke(group, ["list"])
        assert result.exit_code == 0
        assert "Parameters:" in result.output
        assert "x (int)" in result.output
        assert "y (int)" in result.output

    # ------------------------------------------------------------------
    # Dynamic function commands
    # ------------------------------------------------------------------

    def test_cli_dynamic_commands_appear(self, sample_function_info):
        """Functions in the registry become CLI commands."""
        r = self._make_refract_with_function(sample_function_info)
        group = r.cli()
        assert "test_add" in group.commands

    def test_cli_dynamic_command_executes(self, sample_function_info):
        """Dynamic CLI command executes the underlying function."""
        r = self._make_refract_with_function(sample_function_info)
        group = r.cli()
        runner = CliRunner()
        result = runner.invoke(group, ["test_add", "--x", "7", "--y", "3"])
        assert result.exit_code == 0
        assert "10" in result.output  # 7 + 3 = 10

    def test_cli_dynamic_command_help(self, sample_function_info):
        """Dynamic command exposes its parameters in --help."""
        r = self._make_refract_with_function(sample_function_info)
        group = r.cli()
        runner = CliRunner()
        result = runner.invoke(group, ["test_add", "--help"])
        assert result.exit_code == 0
        assert "--x" in result.output
        assert "--y" in result.output
        assert "Add two numbers together" in result.output

    def test_cli_only_includes_cli_interface_functions(self, sample_function_info):
        """Functions without 'cli' interface are not added as commands."""
        from refract import Refract
        api_only_func = FunctionInfo(
            name="api_only",
            func=lambda x: x,
            description="API only function",
            params=[],
            interfaces=["api"],
            return_type=GenericOutput,
        )
        r = Refract("test-project")
        r._registry.append(sample_function_info)   # has 'cli' interface
        r._registry.append(api_only_func)          # no 'cli' interface
        group = r.cli()
        assert "test_add" in group.commands
        assert "api_only" not in group.commands

    # ------------------------------------------------------------------
    # @refract.command() — custom commands
    # ------------------------------------------------------------------

    def test_command_decorator_registers_custom_command(self):
        """@refract.command() stores the command in _custom_commands."""
        from refract import Refract
        r = Refract("test-project")

        @r.command()
        def my_task():
            """A custom task."""
            pass

        assert len(r._custom_commands) == 1
        cmd_name, cmd_func, cmd_kwargs = r._custom_commands[0]
        assert cmd_name == "my-task"
        assert cmd_func is my_task

    def test_command_decorator_default_name_uses_hyphens(self):
        """Function name underscores become hyphens in command name."""
        from refract import Refract
        r = Refract("test-project")

        @r.command()
        def health_check():
            pass

        cmd_name, _, _ = r._custom_commands[0]
        assert cmd_name == "health-check"

    def test_command_decorator_explicit_name(self):
        """Explicit name= overrides the function name."""
        from refract import Refract
        r = Refract("test-project")

        @r.command(name="custom-name")
        def whatever():
            pass

        cmd_name, _, _ = r._custom_commands[0]
        assert cmd_name == "custom-name"

    def test_command_decorator_preserves_original_function(self):
        """@refract.command() returns the original function unchanged."""
        from refract import Refract
        r = Refract("test-project")

        @r.command()
        def my_func():
            return "hello"

        assert my_func() == "hello"

    def test_custom_commands_appear_in_cli_group(self):
        """Custom commands added via @refract.command() appear in cli()."""
        from refract import Refract
        r = Refract("test-project")

        @r.command()
        def health_check():
            """Run health check."""
            click.echo("all good")

        group = r.cli()
        assert "health-check" in group.commands

    def test_custom_command_executes_in_cli_group(self):
        """Custom commands added via @refract.command() are executable."""
        from refract import Refract
        r = Refract("test-project")

        @r.command()
        def say_hello():
            """Greet."""
            click.echo("hello from custom command")

        group = r.cli()
        runner = CliRunner()
        result = runner.invoke(group, ["say-hello"])
        assert result.exit_code == 0
        assert "hello from custom command" in result.output

    def test_multiple_custom_commands(self):
        """Multiple @refract.command() decorators all appear in the group."""
        from refract import Refract
        r = Refract("test-project")

        @r.command()
        def cmd_one():
            pass

        @r.command()
        def cmd_two():
            pass

        @r.command(name="cmd-three")
        def cmd_three_func():
            pass

        group = r.cli()
        assert "cmd-one" in group.commands
        assert "cmd-two" in group.commands
        assert "cmd-three" in group.commands

    # ------------------------------------------------------------------
    # run_cli property
    # ------------------------------------------------------------------

    def test_run_cli_returns_click_group(self):
        """run_cli property returns a Click Group."""
        from refract import Refract
        r = Refract("test-project")
        assert isinstance(r.run_cli, click.Group)

    def test_run_cli_is_callable(self):
        """run_cli returns a callable (required for pyproject.toml entry points)."""
        from refract import Refract
        r = Refract("test-project")
        assert callable(r.run_cli)

    def test_run_cli_returns_same_instance_on_repeated_access(self):
        """run_cli returns the same cached Click group on repeated access."""
        from refract import Refract
        r = Refract("test-project")
        first = r.run_cli
        second = r.run_cli
        assert first is second

    def test_run_cli_includes_standard_commands(self):
        """run_cli group has the same commands as cli()."""
        from refract import Refract
        r = Refract("test-project")
        group = r.run_cli
        assert "list" in group.commands
        assert "serve" in group.commands
        assert "serve-api" in group.commands
        assert "serve-mcp" in group.commands

    # ------------------------------------------------------------------
    # serve-api command
    # ------------------------------------------------------------------

    @patch("uvicorn.run")
    @patch("refract.cli.create_api_app")
    def test_serve_api_calls_uvicorn(self, mock_create_api, mock_uvicorn):
        """serve-api command invokes uvicorn.run with correct parameters."""
        from refract import Refract
        r = Refract("test-project")
        mock_api_app = MagicMock()
        mock_create_api.return_value = mock_api_app

        group = r.cli()
        runner = CliRunner()
        result = runner.invoke(group, ["serve-api", "--host", "0.0.0.0", "--port", "9000"])

        assert result.exit_code == 0
        mock_create_api.assert_called_once_with(r)
        mock_uvicorn.assert_called_once_with(mock_api_app, host="0.0.0.0", port=9000)

    @patch("uvicorn.run")
    @patch("refract.cli.create_api_app")
    def test_serve_api_default_host_port(self, mock_create_api, mock_uvicorn):
        """serve-api uses default host 127.0.0.1 and port 8000."""
        from refract import Refract
        r = Refract("test-project")
        mock_create_api.return_value = MagicMock()

        group = r.cli()
        runner = CliRunner()
        result = runner.invoke(group, ["serve-api"])

        assert result.exit_code == 0
        call_kwargs = mock_uvicorn.call_args[1]
        assert call_kwargs["host"] == "127.0.0.1"
        assert call_kwargs["port"] == 8000

    # ------------------------------------------------------------------
    # Isolation: multiple Refract instances
    # ------------------------------------------------------------------

    def test_two_refract_instances_have_independent_cli_groups(self, sample_function_info):
        """Each Refract instance gets its own isolated CLI group."""
        from refract import Refract
        r1 = Refract("project-a")
        r1._registry.append(sample_function_info)

        r2 = Refract("project-b")  # empty registry

        g1 = r1.cli()
        g2 = r2.cli()

        assert "test_add" in g1.commands
        assert "test_add" not in g2.commands
