#!/usr/bin/env python3
"""
简化版：演示 mistletoe 的核心作用
"""

import mistletoe
from mistletoe.block_token import Heading, Paragraph, Table, List as ListBlock
from mistletoe.span_token import RawText

def explain_mistletoe():
    print("🔍 mistletoe 是什么？")
    print("=" * 50)
    print()
    print("mistletoe 是一个强大的 Python Markdown 解析器，它的核心作用是：")
    print()
    print("1. 📖 将 Markdown 文本解析成结构化的语法树")
    print("2. 🌳 识别文档的语义结构（标题、段落、列表、表格等）")
    print("3. ✂️  让我们能够按照语义边界进行智能分割")
    print("4. 🔄 支持语法树和 Markdown 文本的双向转换")
    print()

def demo_parsing():
    print("📝 Markdown 解析演示")
    print("-" * 30)
    
    # 简单的 Markdown 示例
    markdown = """# 第一章
这是第一章的内容。

## 1.1 小节
这是小节内容。

- 要点1
- 要点2

| 表格 | 数据 |
|------|------|
| A    | 1    |
"""
    
    print("原始 Markdown:")
    print(repr(markdown))
    print()
    
    # 解析成语法树
    doc = mistletoe.Document(markdown)
    
    print("解析后的结构:")
    for i, child in enumerate(doc.children):
        token_type = child.__class__.__name__
        
        if isinstance(child, Heading):
            # 获取标题文本
            if child.children and isinstance(child.children[0], RawText):
                content = child.children[0].content
                print(f"  {i+1}. {token_type} (级别 {child.level}): '{content}'")
            
        elif isinstance(child, Paragraph):
            # 获取段落文本
            if child.children and isinstance(child.children[0], RawText):
                content = child.children[0].content[:20] + "..."
                print(f"  {i+1}. {token_type}: '{content}'")
                
        elif isinstance(child, ListBlock):
            print(f"  {i+1}. {token_type}: {len(child.children)} 个列表项")
            
        elif isinstance(child, Table):
            rows = len(child.children)
            cols = len(child.header.children) if child.header else 0
            print(f"  {i+1}. {token_type}: {rows}行 x {cols}列")
            
        else:
            print(f"  {i+1}. {token_type}")

def compare_splitting():
    print("\n🆚 智能分割 vs 简单分割")
    print("-" * 30)
    
    text = "# 标题\n内容很长很长\n## 子标题\n更多内容"
    
    print("原始文本:", repr(text))
    print()
    
    # 简单分割（按字符数）
    print("❌ 简单字符分割（每20字符）：")
    for i in range(0, len(text), 20):
        chunk = text[i:i+20]
        print(f"   块{i//20+1}: {repr(chunk)}")
    
    print("\n🎯 mistletoe 智能分割（按语义结构）：")
    doc = mistletoe.Document(text)
    for i, child in enumerate(doc.children):
        token_type = child.__class__.__name__
        print(f"   块{i+1}: {token_type}")
    
    print()
    print("✅ 优势：智能分割保持了 Markdown 结构的完整性！")

def explain_chunking_process():
    print("\n🔧 在我们的分割器中，mistletoe 的具体作用")
    print("-" * 30)
    
    steps = [
        "1. 📖 mistletoe.Document(text) - 将输入文本解析成语法树",
        "2. 🔍 遍历语法树的每个块级元素（标题、段落、列表、表格）",
        "3. 📏 计算每个元素的大小（通过 tokenizer）",
        "4. ✂️  根据设定的 chunk_size 决定如何分组",
        "5. 📋 智能处理标题继承（子标题会带上父标题）",
        "6. 📊 特殊处理表格（可转换为段落格式）",
        "7. 🔄 使用 MarkdownRenderer 将语法树重新渲染为 Markdown",
    ]
    
    for step in steps:
        print(f"   {step}")
    
    print()
    print("💡 关键点：整个过程基于 Markdown 的语义结构，而不是简单的文本切割！")

if __name__ == "__main__":
    explain_mistletoe()
    demo_parsing()
    compare_splitting()
    explain_chunking_process() 