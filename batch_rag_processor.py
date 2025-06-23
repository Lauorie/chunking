#!/usr/bin/env python3
"""
批量RAG文档处理脚本

结合批量文档处理和RAG扩展功能，使用自定义tokenizer处理文档并输出RAG友好的格式。
"""

import os
import sys
import json
import time
from pathlib import Path
from typing import List, Dict, Any
import concurrent.futures
from tqdm import tqdm

# 添加当前目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from transformers import PreTrainedTokenizerFast
except ImportError as e:
    print(f"⚠ transformers库未安装: {e}")
    PreTrainedTokenizerFast = None

from chunking import (
    AstMarkdownSplitter, 
    setup_logging, 
    timer, 
    metrics, 
    format_chunk_stats,
    ChunkingError
)


class RAGDocumentProcessor(AstMarkdownSplitter):
    """专为RAG应用优化的文档处理器"""
    
    def __init__(self, tokenizer_path: str = None, **kwargs):
        # --- Tokenizer Initialization (Robust) ---
        tokenizer_func = None
        # First, check if the Hugging Face tokenizer library is available and a path is provided
        if PreTrainedTokenizerFast is not None and tokenizer_path and os.path.exists(tokenizer_path):
            try:
                hf_tokenizer = PreTrainedTokenizerFast(tokenizer_file=tokenizer_path)
                # Create a lambda that matches the expected signature for our splitter
                tokenizer_func = lambda text: hf_tokenizer.encode(text, add_special_tokens=False)
            except Exception as e:
                # This will be printed from within the worker process if it fails
                print(f"⚠ 警告: 无法加载自定义tokenizer '{tokenizer_path}': {e}。将尝试使用tiktoken。")
        
        # If the custom tokenizer failed or wasn't provided, try tiktoken
        if tokenizer_func is None:
            try:
                import tiktoken
                encoding = tiktoken.encoding_for_model("gpt-4o")
                tokenizer_func = encoding.encode
            except (ImportError, FileNotFoundError):
                # This will be printed from within the worker process if it fails
                print("⚠ 警告: tiktoken加载失败。将回退到基于字符的长度计算，分块可能不准确。")
                # Fallback to character-based counting if all else fails
                tokenizer_func = lambda x: list(x)

        # --- Parent Class Initialization ---
        # Build the configuration dictionary for the parent AstMarkdownSplitter
        rag_defaults = {
            'chunk_size': kwargs.get('chunk_size', 800),
            'chunk_overlap': kwargs.get('chunk_overlap', 100),         
            'convert_table_ratio': kwargs.get('convert_table_ratio', 0.2),  
            'enable_first_line_as_title': True,
            'tokenizer': tokenizer_func  # CRITICAL: Pass the successfully loaded tokenizer to the core splitter
        }
        # Allow any further kwargs to override the defaults
        rag_defaults.update(kwargs)
        
        # Initialize the parent class with the correct configuration
        super().__init__(**rag_defaults)
        
        # --- Local Configuration ---
        self._max_chunk_size = rag_defaults['chunk_size']
        # Keep a reference to the tokenizer for local use (e.g., in reporting)
        self._token_counter = tokenizer_func
    
    def process_for_rag(self, text: str, metadata: dict = None) -> List[dict]:
        """处理文档并返回RAG友好的格式"""
        if metadata:
            metadata_str = self._format_metadata(metadata)
            chunks = self.split_text_metadata_aware(text, metadata_str)
        else:
            chunks = self.split_text(text)
        
        # 过滤和合并过小的块
        chunks = self._merge_small_chunks(chunks)
        
        rag_chunks = []
        for i, chunk in enumerate(chunks):
            estimated_tokens = self._count_tokens_safe(chunk)
            rag_chunk = {
                'id': f"chunk_{i:04d}",
                'content': chunk,
                'metadata': metadata or {},
                'chunk_index': i,
                'total_chunks': len(chunks),
                'char_count': len(chunk),
                'estimated_tokens': estimated_tokens,
                'content_type': self._get_chunk_content_tag(chunk),
                'content_hash': hash(chunk) % (10**8),
                'created_at': time.strftime('%Y-%m-%d %H:%M:%S')
            }
            rag_chunks.append(rag_chunk)
        
        return rag_chunks
    
    def _format_metadata(self, metadata: dict) -> str:
        """格式化元数据为字符串"""
        return " | ".join([f"{k}: {v}" for k, v in metadata.items()])
    
    def _count_tokens_safe(self, text: str) -> int:
        """安全的token计数方法，使用缓存管理器确保一致性。"""
        # 使用缓存管理器的方法确保与分块过程中的token计算一致
        return self._cache_manager.get_token_count(text, self._tokenizer)

    def _merge_small_chunks(self, chunks: List[str], min_tokens: int = None) -> List[str]:
        """合并过小的块以提高RAG质量"""
        if not chunks:
            return chunks
        
        # 使用配置的最小块大小，默认50
        if min_tokens is None:
            min_tokens = getattr(self, '_min_chunk_tokens', 50)
        
        merged_chunks = []
        current_chunk = ""
        current_tokens = 0
        
        for i, chunk in enumerate(chunks):
            chunk = chunk.strip()
            if not chunk:  # 跳过空块
                continue
                
            chunk_tokens = self._count_tokens_safe(chunk)
            
            # 特殊处理：如果当前块是小标题（如"# 参考文档"），尝试与下一块合并
            is_small_heading = (chunk_tokens < min_tokens and 
                              chunk.startswith('#') and 
                              i < len(chunks) - 1)  # 不是最后一块
            
            # 如果当前块已经足够大，或者加上新块会超过最大大小（除非是小标题）
            if (current_tokens >= min_tokens and not is_small_heading) or \
               (current_tokens + chunk_tokens > self._max_chunk_size and current_chunk and not is_small_heading):
                if current_chunk:
                    merged_chunks.append(current_chunk.strip())
                current_chunk = chunk
                current_tokens = chunk_tokens
            else:
                # 合并到当前块
                if current_chunk:
                    current_chunk += "\n\n" + chunk
                    current_tokens = self._count_tokens_safe(current_chunk)
                else:
                    current_chunk = chunk
                    current_tokens = chunk_tokens
        
        # 处理最后一个块
        if current_chunk:
            merged_chunks.append(current_chunk.strip())
        
        # 后处理：如果最后一个块太小，尝试与倒数第二个块合并
        if len(merged_chunks) >= 2:
            last_chunk = merged_chunks[-1]
            second_last_chunk = merged_chunks[-2]
            
            last_chunk_tokens = self._count_tokens_safe(last_chunk)
            second_last_tokens = self._count_tokens_safe(second_last_chunk)
            
            # 如果最后一个块太小，且倒数第二个块不超过CHUNK_SIZE
            if (last_chunk_tokens < min_tokens and 
                second_last_tokens <= self._max_chunk_size):
                
                # 尝试合并，检查是否会超过CHUNK_SIZE
                combined_chunk = second_last_chunk + "\n\n" + last_chunk
                combined_tokens = self._count_tokens_safe(combined_chunk)
                
                if combined_tokens <= self._max_chunk_size:
                    # 执行合并：移除最后两个块，添加合并后的块
                    merged_chunks = merged_chunks[:-2] + [combined_chunk]
                    print(f"  💡 最后块合并: {last_chunk_tokens} + {second_last_tokens} = {combined_tokens} tokens")
        
        return merged_chunks

    def _get_chunk_content_tag(self, chunk: str) -> str:
        """分析块内容类型"""
        chunk_lines = chunk.strip().split('\n')
        first_line = chunk_lines[0] if chunk_lines else ""
        
        if '|' in chunk and '---' in chunk:
            return 'table'
        elif first_line.startswith('#'):
            level = len(first_line) - len(first_line.lstrip('#'))
            return f'heading_h{level}'
        elif any(line.strip().startswith(('- ', '* ', '+ ')) for line in chunk_lines):
            return 'unordered_list'
        elif any(line.strip().split('.')[0].isdigit() for line in chunk_lines if '.' in line):
            return 'ordered_list'
        elif '```' in chunk:
            return 'code_block'
        elif any(line.strip().startswith('>') for line in chunk_lines):
            return 'blockquote'
        else:
            return 'paragraph'

    # 继承并确保父类方法可用
    def _process_block_for_splitting(self, child, state, max_chunk_size):
        """重载父类方法以确保兼容性"""
        return super()._process_block_for_splitting(child, state, max_chunk_size)
    
    def _handle_block_fits_current_chunk(self, block_content, block_size, state, max_chunk_size):
        """重载父类方法以确保兼容性"""
        return super()._handle_block_fits_current_chunk(block_content, block_size, state, max_chunk_size)
    
    def _handle_block_fits_next_chunk(self, child, block_size, state, children_to_process, max_chunk_size):
        """重载父类方法以确保兼容性"""
        return super()._handle_block_fits_next_chunk(child, block_size, state, children_to_process, max_chunk_size)

def extract_file_metadata(file_path: Path) -> Dict[str, Any]:
    """从文件路径和内容中提取元数据"""
    stat = file_path.stat()
    
    metadata = {
        'filename': file_path.name,
        'filepath': str(file_path),
        'file_size': stat.st_size,
        'created_time': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(stat.st_ctime)),
        'modified_time': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(stat.st_mtime)),
        'file_extension': file_path.suffix.lower()
    }
    
    # 尝试从文件内容提取更多元数据
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # 统计信息
        metadata.update({
            'char_count': len(content),
            'line_count': content.count('\n') + 1,
            'word_count': len(content.split()),
            'paragraph_count': len([p for p in content.split('\n\n') if p.strip()]),
            'heading_count': content.count('#'),
            'table_count': content.count('|'),
            'code_block_count': content.count('```') // 2
        })
        
        # 提取第一行作为可能的标题
        first_line = content.split('\n')[0].strip()
        if first_line:
            if first_line.startswith('#'):
                metadata['document_title'] = first_line.lstrip('#').strip()
            else:
                metadata['document_title'] = first_line[:100]  # 截取前100字符
                
    except Exception as e:
        print(f"⚠ 提取文件元数据失败 {file_path.name}: {e}")
    
    return metadata


def save_rag_chunks_to_json(rag_chunks: List[dict], output_file: Path, source_metadata: dict):
    """保存RAG块到JSON格式"""
    
    # 计算总体统计信息
    total_tokens = sum(chunk['estimated_tokens'] for chunk in rag_chunks)
    content_types = {}
    for chunk in rag_chunks:
        content_type = chunk['content_type']
        content_types[content_type] = content_types.get(content_type, 0) + 1
    
    result = {
        'document_info': {
            'source_file': source_metadata['filename'],
            'source_path': source_metadata['filepath'],
            'processed_at': time.strftime('%Y-%m-%d %H:%M:%S'),
            'processor_version': '1.0.0'
        },
        'source_metadata': source_metadata,
        'chunking_summary': {
            'total_chunks': len(rag_chunks),
            'total_estimated_tokens': total_tokens,
            'avg_tokens_per_chunk': total_tokens / len(rag_chunks) if rag_chunks else 0,
            'content_type_distribution': content_types,
            'chunk_size_stats': {
                'min_chars': min(chunk['char_count'] for chunk in rag_chunks) if rag_chunks else 0,
                'max_chars': max(chunk['char_count'] for chunk in rag_chunks) if rag_chunks else 0,
                'avg_chars': sum(chunk['char_count'] for chunk in rag_chunks) / len(rag_chunks) if rag_chunks else 0
            }
        },
        'chunks': rag_chunks
    }
    
    # 确保输出目录存在
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    # 保存为JSON文件
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)


def process_file_worker(doc_file_path_str: str, rag_processor_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    一个独立的worker函数，用于在子进程中处理单个文件。
    此函数现在包含完整的错误捕获和追溯功能。
    """
    try:
        doc_file = Path(doc_file_path_str)
        
        # 在worker内部初始化处理器，这是并行处理的关键
        rag_processor = RAGDocumentProcessor(
            tokenizer_path=rag_processor_config.get("tokenizer_path"),
            chunk_size=rag_processor_config.get("chunk_size"),
            chunk_overlap=rag_processor_config.get("chunk_overlap"),
            convert_table_ratio=rag_processor_config.get("convert_table_ratio")
        )
        # 设置最小块大小
        rag_processor._min_chunk_tokens = rag_processor_config.get("min_chunk_tokens", 50)
        
        output_dir = Path(rag_processor_config["output_dir"])

        with open(doc_file, 'r', encoding='utf-8') as f:
            content = f.read()

        if not content.strip():
            return {'status': 'skipped', 'file': doc_file.name, 'reason': '空文件'}

        file_metadata = extract_file_metadata(doc_file)
        rag_chunks = rag_processor.process_for_rag(content, file_metadata)

        if not rag_chunks:
            return {'status': 'skipped', 'file': doc_file.name, 'reason': '未生成任何块'}

        output_file = output_dir / f"{doc_file.stem}_rag_chunks.json"
        save_rag_chunks_to_json(rag_chunks, output_file, file_metadata)

        chunk_stats_str = format_chunk_stats([chunk['content'] for chunk in rag_chunks])
        token_count = sum(chunk['estimated_tokens'] for chunk in rag_chunks)

        return {
            'status': 'success',
            'file': doc_file.name,
            'chunk_count': len(rag_chunks),
            'token_count': token_count,
            'stats_str': f"{chunk_stats_str}, Tokens: {token_count}"
        }

    except Exception as e:
        import traceback
        # 捕获并返回完整的错误信息和堆栈，以便于主进程诊断问题
        error_str = f"处理 {Path(doc_file_path_str).name} 时发生致命错误: {e}\n{traceback.format_exc()}"
        # 也在worker进程中打印错误，便于调试
        print(f"[WORKER ERROR] {error_str}")
        return {'status': 'failure', 'file': Path(doc_file_path_str).name, 'error': error_str}

def process_document_batch_rag(
    data_dir: str, 
    output_dir: str = None,  # 新增输出目录参数
    tokenizer_path: str = None,
    chunk_size: int = 512,
    chunk_overlap: int = 50,
    convert_table_ratio: float = 0.3,
    min_chunk_tokens: int = 50
):
    """批量处理文档并生成RAG友好的输出"""
    
    data_path = Path(data_dir)
    if not data_path.exists():
        raise FileNotFoundError(f"数据目录不存在: {data_dir}")
    
    # 创建输出目录
    if output_dir:
        output_path = Path(output_dir)
    else:
        output_path = data_path / "rag_chunks"  # 默认输出目录
    output_path.mkdir(parents=True, exist_ok=True)
    
    # 将RAG处理器配置打包，以便传递给worker
    rag_processor_config = {
        "tokenizer_path": tokenizer_path,
        "chunk_size": chunk_size,
        "chunk_overlap": chunk_overlap,
        "convert_table_ratio": convert_table_ratio,
        "min_chunk_tokens": min_chunk_tokens,
        "output_dir": str(output_path)  # 使用新的输出目录
    }
    
    # 重置性能指标
    metrics.reset()
    
    # 查找所有支持的文档文件
    supported_extensions = ['.md', '.txt', '.markdown', '.rst']
    doc_files = []
    for ext in supported_extensions:
        doc_files.extend(data_path.glob(f"**/*{ext}"))
    
    if not doc_files:
        print(f"⚠ 在 {data_dir} 中未找到支持的文档文件 ({', '.join(supported_extensions)})")
        return
    
    print(f"📁 找到 {len(doc_files)} 个文档文件")
    print(f"📁 输入目录: {data_dir}")
    print(f"📁 输出目录: {output_path}")
    print(f"🔧 配置: chunk_size={chunk_size}, chunk_overlap={chunk_overlap}, convert_table_ratio={convert_table_ratio}")
    print(f"📏 最小块大小: {min_chunk_tokens} tokens (低于此值的块将被合并)")
    print(f"📊 tokenizer: {'自定义' if tokenizer_path else '默认'}")
    # 限制并行度为32，平衡性能和稳定性
    max_workers = min(32, os.cpu_count() or 1)
    print(f"⚙️  并行数: {max_workers} 个进程 (限制为32)")
    print("-" * 60)
    
    processed_count = 0
    failed_count = 0
    skipped_count = 0
    total_chunks = 0
    
    with timer(f"并行RAG处理 {len(doc_files)} 个文档"), concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
        # 创建futures列表，将任务提交给进程池
        futures = [executor.submit(process_file_worker, str(doc_file), rag_processor_config) for doc_file in doc_files]

        # 使用tqdm来显示进度条
        for future in tqdm(concurrent.futures.as_completed(futures), total=len(doc_files), desc="处理文档"):
            try:
                result = future.result()
                if result['status'] == 'success':
                    # print(f"✓ {result['file']}: {result['stats_str']}") # 进度条存在时，这行可以注释掉以保持输出整洁
                    processed_count += 1
                    total_chunks += result['chunk_count']
                elif result['status'] == 'skipped':
                    print(f"⚠ {result['file']}: 跳过 ({result['reason']})")
                    skipped_count += 1
                else: # failure
                    print(f"✗ {result['file']}: 失败 ({result['error']})")
                    failed_count += 1
            except Exception as e:
                # future.result() 本身也可能抛出异常
                print(f"✗ 一个worker进程发生严重错误: {e}")
                failed_count += 1

    # 显示总体统计
    print("-" * 60)
    print("📈 批量处理完成统计:")
    print(f"  ✓ 成功处理: {processed_count} 个文件")
    print(f"  ⚠ 处理跳过: {skipped_count} 个文件")
    print(f"  ✗ 处理失败: {failed_count} 个文件")
    print(f"  📦 总生成块数: {total_chunks}")
    print(f"  📁 输出目录: {output_path}")
    
    # 性能指标
    # 注意：metrics模块在子进程中更新的数据不会反映在主进程中。
    # 这里的性能指标只反映了任务提交和结果收集的时间，而不是实际的文件处理时间。
    # 更准确的性能分析应基于tqdm的速率或处理报告中的总耗时。
    print(f"  ⏱ 总体处理耗时（包括任务调度）在上面的 'timer' 中显示。")
    
    # 收集所有块的token统计
    all_chunk_tokens = []
    all_chunk_chars = []
    oversized_chunks = []
    file_chunk_stats = {}
    
    # 重新扫描所有生成的文件以收集token统计
    for json_file in output_path.glob("*_rag_chunks.json"):
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                chunks = data.get('chunks', [])
                
                file_tokens = []
                file_chars = []
                file_oversized = []
                
                for chunk in chunks:
                    token_count = chunk.get('estimated_tokens', 0)
                    char_count = chunk.get('char_count', 0)
                    
                    all_chunk_tokens.append(token_count)
                    all_chunk_chars.append(char_count)
                    file_tokens.append(token_count)
                    file_chars.append(char_count)
                    
                    # 检查超长块（超过配置chunk_size的120%）
                    if token_count > chunk_size * 1.2:
                        oversized_info = {
                            'file': json_file.stem,
                            'chunk_id': chunk.get('chunk_id', 'unknown'),
                            'token_count': token_count,
                            'char_count': char_count,
                            'content_preview': chunk.get('content', '')[:100] + '...'
                        }
                        oversized_chunks.append(oversized_info)
                        file_oversized.append(oversized_info)
                
                # 文件级别统计
                if file_tokens:
                    file_chunk_stats[json_file.stem] = {
                        'chunk_count': len(file_tokens),
                        'token_stats': {
                            'min': min(file_tokens),
                            'max': max(file_tokens),
                            'avg': sum(file_tokens) / len(file_tokens),
                            'total': sum(file_tokens)
                        },
                        'char_stats': {
                            'min': min(file_chars),
                            'max': max(file_chars),
                            'avg': sum(file_chars) / len(file_chars),
                            'total': sum(file_chars)
                        },
                        'oversized_chunks': len(file_oversized),
                        'oversized_details': file_oversized
                    }
        except Exception as e:
            print(f"⚠ 无法读取统计文件 {json_file}: {e}")
    
    # 计算全局token统计
    token_statistics = {}
    if all_chunk_tokens:
        token_statistics = {
            'total_chunks': len(all_chunk_tokens),
            'token_distribution': {
                'min': min(all_chunk_tokens),
                'max': max(all_chunk_tokens),
                'avg': sum(all_chunk_tokens) / len(all_chunk_tokens),
                'median': sorted(all_chunk_tokens)[len(all_chunk_tokens)//2],
                'total': sum(all_chunk_tokens)
            },
            'char_distribution': {
                'min': min(all_chunk_chars),
                'max': max(all_chunk_chars),
                'avg': sum(all_chunk_chars) / len(all_chunk_chars),
                'median': sorted(all_chunk_chars)[len(all_chunk_chars)//2],
                'total': sum(all_chunk_chars)
            },
            'chunk_size_analysis': {
                'within_limit': sum(1 for t in all_chunk_tokens if t <= chunk_size),
                'slightly_over': sum(1 for t in all_chunk_tokens if chunk_size < t <= chunk_size * 1.2),
                'significantly_over': sum(1 for t in all_chunk_tokens if t > chunk_size * 1.2),
                'oversized_percentage': (sum(1 for t in all_chunk_tokens if t > chunk_size * 1.2) / len(all_chunk_tokens)) * 100,
                'too_small': sum(1 for t in all_chunk_tokens if t < min_chunk_tokens),
                'too_small_percentage': (sum(1 for t in all_chunk_tokens if t < min_chunk_tokens) / len(all_chunk_tokens)) * 100
            },
            'quality_indicators': {
                'avg_utilization': (sum(all_chunk_tokens) / len(all_chunk_tokens)) / chunk_size * 100,
                'size_consistency': 100 - (max(all_chunk_tokens) - min(all_chunk_tokens)) / chunk_size * 100 if chunk_size > 0 else 0,
                'oversized_alert': len(oversized_chunks) > 0
            }
        }

    # 生成处理报告
    report_file = output_path / "processing_report.json"
    report = {
        'processing_summary': {
            'total_files': len(doc_files),
            'processed_files': processed_count,
            'failed_files': failed_count,
            'total_chunks_generated': total_chunks,
            'processing_time': time.strftime('%Y-%m-%d %H:%M:%S'),
            'configuration': {
                'chunk_size': chunk_size,
                'chunk_overlap': chunk_overlap,
                'convert_table_ratio': convert_table_ratio,
                'min_chunk_tokens': min_chunk_tokens,
                'tokenizer_path': tokenizer_path
            }
        },
        'token_statistics': token_statistics,
        'oversized_chunks_alert': {
            'count': len(oversized_chunks),
            'severity': 'HIGH' if len(oversized_chunks) > total_chunks * 0.1 else 'MEDIUM' if len(oversized_chunks) > 0 else 'NONE',
            'details': oversized_chunks[:10],  # 只显示前10个超长块
            'recommendation': 'Consider reducing chunk_size or improving content splitting logic' if len(oversized_chunks) > 0 else 'Chunk sizes are within acceptable limits'
        },
        'file_level_statistics': file_chunk_stats,
        'performance_metrics': metrics.get_summary(),
        'processed_files': [f.name for f in doc_files[:processed_count]],
        'failed_files': [f.name for f in doc_files[processed_count:processed_count+failed_count]] if failed_count > 0 else []
    }
    
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    print(f"  📋 处理报告: {report_file}")
    
    # 显示token统计摘要
    if token_statistics:
        print("\n🔍 Token统计摘要:")
        token_dist = token_statistics['token_distribution']
        chunk_analysis = token_statistics['chunk_size_analysis']
        quality = token_statistics['quality_indicators']
        
        print(f"  📊 Token分布: 最小{token_dist['min']}, 最大{token_dist['max']}, 平均{token_dist['avg']:.1f}")
        print(f"  📏 块大小分析: 正常{chunk_analysis['within_limit']}, 略超{chunk_analysis['slightly_over']}, 严重超{chunk_analysis['significantly_over']}, 过小{chunk_analysis['too_small']}")
        print(f"  📈 质量指标: 利用率{quality['avg_utilization']:.1f}%, 一致性{quality['size_consistency']:.1f}%")
        
        # 显示小块合并效果
        if chunk_analysis['too_small'] > 0:
            print(f"  ⚠️  小块警告: {chunk_analysis['too_small']}个块小于{min_chunk_tokens} tokens ({chunk_analysis['too_small_percentage']:.1f}%)")
            print(f"     建议增加min_chunk_tokens或检查合并逻辑")
        else:
            print(f"  ✅ 小块检查: 所有块都符合最小大小要求(≥{min_chunk_tokens} tokens)")
        
        # 超长块警告
        if len(oversized_chunks) > 0:
            severity = report['oversized_chunks_alert']['severity']
            severity_emoji = "🔴" if severity == "HIGH" else "🟡" if severity == "MEDIUM" else "🟢"
            print(f"  {severity_emoji} 超长块警告: {len(oversized_chunks)}个块超过限制({severity})")
            if len(oversized_chunks) <= 3:
                for chunk in oversized_chunks:
                    print(f"    - {chunk['file']}: {chunk['token_count']} tokens ({chunk['char_count']} chars)")
        else:
            print(f"  ✅ 块大小检查: 所有块都在可接受范围内")


def main():
    """主函数"""
    # 设置日志
    setup_logging(level="INFO")
    
    # 配置参数
    DATA_DIR = "/ALL"  # 输入目录
    OUTPUT_DIR = "/chunks"  # 输出目录
    TOKENIZER_PATH = "/tokenizer.json"
    
    # 处理参数（优化超大表格分块）
    CHUNK_SIZE = 1024        # 减小chunk_size，避免超大块
    CHUNK_OVERLAP = 204      # 适中的重叠
    CONVERT_TABLE_RATIO = 0.3  # 降低阈值，更激进地转换表格为段落
    MIN_CHUNK_TOKENS = 64    # 最小块大小，低于此值将被合并
    
    print("🚀 启动批量RAG文档处理")
    print(f"📁 输入目录: {DATA_DIR}")
    print(f"📁 输出目录: {OUTPUT_DIR}")
    print(f"🔧 Tokenizer: {TOKENIZER_PATH}")
    print(f"⚙️  参数: chunk_size={CHUNK_SIZE}, overlap={CHUNK_OVERLAP}, table_ratio={CONVERT_TABLE_RATIO}, min_tokens={MIN_CHUNK_TOKENS}")
    print("=" * 60)
    
    try:
        # 检查tokenizer文件
        if not os.path.exists(TOKENIZER_PATH):
            print(f"⚠ Tokenizer文件不存在: {TOKENIZER_PATH}")
            print("  将使用默认tokenizer")
            TOKENIZER_PATH = None
        
        # 执行批量处理
        process_document_batch_rag(
            data_dir=DATA_DIR,
            output_dir=OUTPUT_DIR,
            tokenizer_path=TOKENIZER_PATH,
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
            convert_table_ratio=CONVERT_TABLE_RATIO,
            min_chunk_tokens=MIN_CHUNK_TOKENS
        )
        
        print("\n🎉 批量RAG处理完成！")
        
    except KeyboardInterrupt:
        print("\n⚠ 用户中断处理")
    except Exception as e:
        print(f"\n❌ 处理失败: {e}")
        raise


if __name__ == "__main__":
    main() 
