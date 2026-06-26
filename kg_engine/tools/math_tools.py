"""LangChain 1.0 math tools for RAG agent.

Simple arithmetic operations useful for calculations related to knowledge base content,
configuration values, quotas, sizing, and other numeric operations.
"""
from __future__ import annotations

import cmath

from langchain.tools import ToolRuntime, tool
from pydantic import BaseModel, Field

from kg_engine.utils.context_tracker import AgentContext


class AddSchema(BaseModel):
    """Schema for addition operation."""

    a: float = Field(..., description="First number. Integer OR float.")
    b: float = Field(..., description="Second number. Integer OR float.")


class SubtractSchema(BaseModel):
    """Schema for subtraction operation."""

    a: float = Field(..., description="Minuend. Integer OR float.")
    b: float = Field(..., description="Subtrahend. Integer OR float.")


class MultiplySchema(BaseModel):
    """Schema for multiplication operation."""

    a: float = Field(..., description="First number. Integer OR float.")
    b: float = Field(..., description="Second number. Integer OR float.")


class DivideSchema(BaseModel):
    """Schema for division operation."""

    dividend: float = Field(..., description="Integer OR float.")
    divisor: float = Field(..., description="Non-zero. Integer OR float.")


class PowerSchema(BaseModel):
    """Schema for exponentiation operation."""

    base: float = Field(..., description="Integer OR float.")
    exponent: float = Field(..., description="Integer OR float.")


class SquareRootSchema(BaseModel):
    """Schema for square root operation."""

    number: float = Field(..., description="Integer OR float. Negative returns complex.")


class ModulusSchema(BaseModel):
    """Schema for modulus (remainder) operation."""

    dividend: int = Field(..., description="Only integer.")
    divisor: int = Field(..., description="Non-zero. Only integer.")


@tool("add", args_schema=AddSchema)
def add(
    a: float,
    b: float,
    runtime: ToolRuntime[AgentContext, None] | None = None,
) -> float:
    """Add two numbers.

    Use for calculating sums, totals, or combining numeric values from knowledge base content.
    """
    return float(a) + float(b)


@tool("subtract", args_schema=SubtractSchema)
def subtract(
    a: float,
    b: float,
    runtime: ToolRuntime[AgentContext, None] | None = None,
) -> float:
    """Subtract second number from first.

    Use for calculating differences, remaining capacity, or deltas.
    """
    return float(a) - float(b)


@tool("multiply", args_schema=MultiplySchema)
def multiply(
    a: float,
    b: float,
    runtime: ToolRuntime[AgentContext, None] | None = None,
) -> float:
    """Multiply two numbers.

    Use for calculating products, scaling values, or multiplication operations.
    """
    return float(a) * float(b)


@tool("divide", args_schema=DivideSchema)
def divide(
    dividend: float,
    divisor: float,
    runtime: ToolRuntime[AgentContext, None] | None = None,
) -> float:
    """Divide dividend by divisor.

    Use for calculating ratios, averages, or division operations.
    Raises ValueError if divisor is zero.
    """
    divisor_float = float(divisor)
    if divisor_float == 0:
        raise ValueError("Cannot divide by zero")
    return float(dividend) / divisor_float


@tool("power", args_schema=PowerSchema)
def power(
    base: float,
    exponent: float,
    runtime: ToolRuntime[AgentContext, None] | None = None,
) -> float:
    """Raise base to exponent power.

    Use for exponential calculations, powers, or raising numbers to exponents.
    """
    return float(base) ** float(exponent)


@tool("square_root", args_schema=SquareRootSchema)
def square_root(
    number: float,
    runtime: ToolRuntime[AgentContext, None] | None = None,
) -> float | complex:
    """Compute square root of number.

    Returns complex number if input is negative.
    """
    number_float = float(number)
    if number_float >= 0:
        return number_float ** 0.5
    return cmath.sqrt(number_float)


@tool("modulus", args_schema=ModulusSchema)
def modulus(
    dividend: int,
    divisor: int,
    runtime: ToolRuntime[AgentContext, None] | None = None,
) -> int:
    """Compute modulus (remainder) of two integers.

    Use for modulo operations, finding remainders, or cyclic calculations.
    Raises ValueError if divisor is zero.
    """
    divisor_int = int(divisor)
    if divisor_int == 0:
        raise ValueError("Cannot divide by zero")
    return int(dividend) % divisor_int

