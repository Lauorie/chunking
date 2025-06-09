"""
Table splitting strategy.

This module handles the splitting of table blocks, including conversion
to paragraphs for oversized tables.
"""

import logging
import re
from typing import List, TYPE_CHECKING

from .base_strategy import BlockSplitStrategy
from ..config import CONFIG
from ..core.exceptions import DocumentParsingError

if TYPE_CHECKING:
    from mistletoe.block_token import BlockToken, Table, TableRow

logger = logging.getLogger(__name__)


class TableSplitStrategy(BlockSplitStrategy):
    """Strategy for splitting table blocks."""
    
    def can_handle(self, block: "BlockToken") -> bool:
        """Check if this is a table block."""
        from mistletoe.block_token import Table
        return isinstance(block, Table)
    
    def split_block(self, block: "Table") -> List["BlockToken"]:
        """
        Split a table block into smaller tables or convert to paragraphs.
        
        Args:
            block: The table block to split
            
        Returns:
            List of split table blocks or paragraph blocks
        """
        try:
            if not hasattr(block, 'header') or not block.header:
                logger.warning("Malformed table found, applying fallback")
                return [block]

            table_header_size = self._count_token_table_row(block.header)
            table_row_sizes = [self._count_token_table_row(row) for row in block.children]

            if not table_row_sizes:
                return [block]

            # Check if header is much larger than average row
            mean_row_size = sum(table_row_sizes) / len(table_row_sizes) if table_row_sizes else 0
            should_replace_header = table_header_size > mean_row_size * CONFIG.max_header_to_row_ratio
            
            if should_replace_header:
                # Replace header with generated one
                cell_count = len(block.header.children) if hasattr(block.header, 'children') else 1
                block = self._replace_table_header(block, cell_count)
                table_row_sizes.insert(0, table_header_size)

            # Check if table should be converted to paragraphs
            max_row_size = max(table_row_sizes) if table_row_sizes else 0
            total_table_size = sum(table_row_sizes) + table_header_size
            
            should_convert = (
                max_row_size >= self.chunk_size * 0.5 or  # Adjust threshold
                total_table_size > self.chunk_size * 2 or
                len(table_row_sizes) > 50
            )
            
            if should_convert:
                logger.info(f"Converting large table to paragraphs: max_row={max_row_size}, total_size={total_table_size}")
                return self._convert_table_to_paragraphs(block)

            # Split table by rows
            return self._split_table_by_rows(block)
            
        except Exception as e:
            logger.error(f"Table splitting failed: {e}")
            return [block]
    
    def _count_token_table_row(self, table_row: "TableRow") -> int:
        """
        Count tokens in a table row.
        
        Args:
            table_row: The table row to count
            
        Returns:
            Number of tokens in the row
        """
        try:
            row_size = CONFIG.table_border_tokens
            
            if not hasattr(table_row, 'children') or table_row.children is None:
                return max(0, row_size - 1)

            for cell in table_row.children:
                if not hasattr(cell, 'children') or cell.children is None:
                    continue
                cell_content = self._get_raw_text(cell.children)
                row_size += self.get_token_count(cell_content)
                row_size += CONFIG.table_cell_separator_tokens
            
            row_size -= 1  # Remove last separator
            return max(0, row_size)
        except Exception as e:
            logger.error(f"Failed to count tokens in table row: {e}")
            return CONFIG.table_border_tokens * 2  # Conservative fallback
    
    def _get_raw_text(self, tokens) -> str:
        """Extract raw text from span tokens."""
        if tokens is None:
            return ""

        from mistletoe.span_token import RawText
        s = ""
        for token in tokens:
            try:
                if isinstance(token, RawText):
                    s += token.content
                if hasattr(token, "children") and token.children is not None:
                    s += self._get_raw_text(token.children)
            except (AttributeError, TypeError):
                continue
        return s
    
    def _replace_table_header(self, table: "Table", cell_count: int) -> "Table":
        """Replace table header with a generated one."""
        try:
            from mistletoe.block_token import TableRow
            # Generate simple headers like C_A, C_B, etc.
            headers = self._gen_table_header(cell_count)
            header_text = f"| {' | '.join(headers)} |"
            
            # Insert original header as first row
            table.children.insert(0, table.header)
            
            # Create new header
            table.header = TableRow(header_text)
            return table
        except Exception as e:
            logger.warning(f"Failed to replace table header: {e}")
            return table
    
    def _gen_table_header(self, size: int) -> List[str]:
        """Generate table headers in format C_A, C_B, C_C, etc."""
        if size <= 0:
            return []
            
        headers = []
        for i in range(size):
            if i < 26:
                headers.append(chr(ord("A") + i))
            else:
                first_char = chr(ord('A') + i // 26 - 1)
                second_char = chr(ord('A') + i % 26)
                headers.append(f"{first_char}{second_char}")
        
        return [f"C_{x}" for x in headers]
    
    def _convert_table_to_paragraphs(self, table: "Table") -> List["BlockToken"]:
        """Convert table to paragraph blocks."""
        try:
            from mistletoe.block_token import Document
            
            # Simple conversion: each row becomes a paragraph
            paragraphs = []
            for row in table.children:
                row_text = self.render_block(row)
                # Clean up table formatting
                row_text = re.sub(r'\|', ' ', row_text)
                row_text = re.sub(r'\s+', ' ', row_text).strip()
                
                if row_text:
                    doc = Document(row_text)
                    if doc.children:
                        paragraphs.append(doc.children[0])
            
            return paragraphs if paragraphs else [table]
            
        except Exception as e:
            logger.error(f"Failed to convert table to paragraphs: {e}")
            return [table]
    
    def _split_table_by_rows(self, table: "Table") -> List["Table"]:
        """Split table by grouping rows that fit within chunk size."""
        if not hasattr(table, 'children') or not table.children:
            return [table]
        
        try:
            from mistletoe.block_token import Document
            
            # Calculate header size
            header_size = self._count_token_table_row(table.header)
            
            result_tables = []
            current_rows = []
            current_size = header_size
            
            for row in table.children:
                row_size = self._count_token_table_row(row)
                
                # Check if adding this row would exceed chunk size
                if current_size + row_size > self.chunk_size and current_rows:
                    # Create new table with current rows
                    new_table = self._create_table_with_rows(table, current_rows)
                    if new_table:
                        result_tables.append(new_table)
                    
                    current_rows = [row]
                    current_size = header_size + row_size
                else:
                    current_rows.append(row)
                    current_size += row_size
            
            # Add last table
            if current_rows:
                new_table = self._create_table_with_rows(table, current_rows)
                if new_table:
                    result_tables.append(new_table)
            
            return result_tables if result_tables else [table]
            
        except Exception as e:
            logger.error(f"Failed to split table by rows: {e}")
            return [table]
    
    def _create_table_with_rows(self, original_table: "Table", rows: List) -> "Table":
        """Create a new table with specified rows."""
        try:
            from mistletoe.block_token import Document
            
            # Create minimal table markdown
            header_cells = len(original_table.header.children) if hasattr(original_table.header, 'children') else 1
            header_line = '|' + ' |' * header_cells
            separator_line = '|' + ' --- |' * header_cells
            markdown_string = f"{header_line}\n{separator_line}\n"
            
            # Parse to get new table structure
            parsed_doc = Document(markdown_string)
            if not parsed_doc.children:
                return None
                
            new_table = parsed_doc.children[0]
            
            # Copy properties from original table
            new_table.header = original_table.header
            if hasattr(original_table, 'column_align'):
                new_table.column_align = original_table.column_align
            new_table.children = rows
            
            return new_table
            
        except Exception as e:
            logger.error(f"Failed to create table with rows: {e}")
            return None 