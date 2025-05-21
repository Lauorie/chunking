import requests
import tiktoken
import json
from tqdm import tqdm
from typing import List, Set, Optional
from loguru import logger

DEFAULT_INPUT_JSON_PATH = "/root/app/academic-test/merged/academic_test_merged_97_web_extract.json"
DEFAULT_OUTPUT_JSON_PATH = "/root/app/academic-test/merged/academic_test_merged_97_web_extract_scored.json"
DEFAULT_CHUNK_MIN_LENGTH = 50
DEFAULT_CHUNK_MAX_LENGTH = 220
DEFAULT_SCORE_API_URL = "http://localhost:8080/v1/score"

class TextChunker:
    """
    A class for splitting text into semantically meaningful chunks based on sentence terminators
    while controlling the token length of each chunk.
    """
    
    # Default terminators for sentence boundaries across multiple languages
    DEFAULT_TERMINATORS = {
        "。", "？", "！", "；", "……", "…", "》", "】", "）",
        "?", "!", ";", "…", ")", "]", "}", ".", "\n\n"
    }
    
    def __init__(
        self, 
        encoding_name: str = "gpt-4o",
        terminators: Optional[Set[str]] = None,
        min_length: int = 128,
        max_length: int = 512
    ):
        """
        Initialize the TextChunker.
        
        Args:
            encoding_name: The name of the tiktoken encoding to use
            terminators: Set of characters that mark sentence boundaries
            min_length: Minimum token length for a chunk
            max_length: Maximum token length for a chunk
        """
        try:
            self.tokenizer = tiktoken.encoding_for_model(encoding_name)
        except Exception as e:
            raise ValueError(f"Failed to initialize tokenizer with encoding '{encoding_name}': {e}")
            
        self.terminators = terminators if terminators is not None else self.DEFAULT_TERMINATORS
        self.min_length = min_length
        self.max_length = max_length
        
        if min_length >= max_length:
            raise ValueError(f"min_length ({min_length}) must be less than max_length ({max_length})")
            
        if min_length < 1:
            raise ValueError(f"min_length ({min_length}) must be at least 1")
    
    def split_into_sentences(self, tokens: List[int]) -> List[List[int]]:
        """
        Split tokens into sentences based on terminators.
        
        Args:
            tokens: List of token IDs
            
        Returns:
            List of token lists, each representing a sentence
        """
        sentences = []
        last_idx = 0
        
        for i, token in enumerate(tokens):
            token_text = self.tokenizer.decode([token])
            if token_text in self.terminators:
                if i + 1 > last_idx:  # Ensure sentence is not empty
                    sentences.append(tokens[last_idx:i+1])
                    last_idx = i + 1
        
        # Handle the last sentence which might not have a terminator
        if last_idx < len(tokens):
            sentences.append(tokens[last_idx:])
            
        return sentences
    
    def merge_sentences_into_chunks(self, sentences: List[List[int]]) -> List[str]:
        """
        Merge sentences into chunks while respecting min and max length constraints.
        Operates on token lists internally and decodes at the end for efficiency.
        
        Args:
            sentences: List of token lists representing sentences
            
        Returns:
            List of text chunks
        """
        token_chunks: List[List[int]] = []
        current_chunk_tokens: List[int] = []
        
        for sentence_tokens in sentences:
            # Ensure current_chunk_tokens, if it became very long from a previous assignment, is split first.
            while len(current_chunk_tokens) > self.max_length:
                token_chunks.append(list(current_chunk_tokens[:self.max_length]))
                current_chunk_tokens = current_chunk_tokens[self.max_length:]

            if len(current_chunk_tokens) + len(sentence_tokens) <= self.max_length:
                current_chunk_tokens.extend(sentence_tokens)
            else:
                # Current chunk + new sentence is too long.
                if len(current_chunk_tokens) >= self.min_length:
                    # Current chunk is valid, save it.
                    token_chunks.append(list(current_chunk_tokens))
                    current_chunk_tokens = list(sentence_tokens) # New sentence starts a new potential chunk
                else:
                    # Current chunk is too short (< min_length).
                    # Fill it with the start of sentence_tokens up to max_length.
                    if len(current_chunk_tokens) < self.max_length: # Ensure there's space to add
                        space_left = self.max_length - len(current_chunk_tokens)
                        current_chunk_tokens.extend(sentence_tokens[:space_left])
                        # Remainder of sentence_tokens starts the new current_chunk_tokens
                        sentence_tokens_remainder = sentence_tokens[space_left:]
                    else: # current_chunk_tokens is already at max_length (should be rare here due to outer while loop)
                        sentence_tokens_remainder = list(sentence_tokens)

                    token_chunks.append(list(current_chunk_tokens)) # This chunk is now full or was already full
                    current_chunk_tokens = sentence_tokens_remainder
        
        # Handle the last remaining current_chunk_tokens
        # First, split it if it's too long
        while len(current_chunk_tokens) > self.max_length:
            token_chunks.append(list(current_chunk_tokens[:self.max_length]))
            current_chunk_tokens = current_chunk_tokens[self.max_length:]

        if current_chunk_tokens: # If there's anything left
            if len(current_chunk_tokens) >= self.min_length:
                token_chunks.append(list(current_chunk_tokens))
            elif token_chunks:  # If last chunk is too short but not empty, and previous chunks exist
                if len(token_chunks[-1]) + len(current_chunk_tokens) <= self.max_length:
                    token_chunks[-1].extend(current_chunk_tokens)
                else:
                    # If we can't merge, add it if it's not "too small" (original heuristic)
                    if len(current_chunk_tokens) > self.min_length // 2:
                        token_chunks.append(list(current_chunk_tokens))
            elif len(current_chunk_tokens) > self.min_length // 2: # No previous chunks, but this one is not "extremely" small
                 token_chunks.append(list(current_chunk_tokens))
            # else: the very small remaining chunk is dropped if it doesn't meet conditions.
        
        # Decode all token_chunks to strings, filtering out any potentially empty lists
        final_chunks = [self.tokenizer.decode(chunk) for chunk in token_chunks if chunk]
        return final_chunks
    
    def split_text(self, text: str, allowed_special: Optional[Set[str]] = None) -> List[str]:
        """
        Split text into semantically meaningful chunks.
        
        Args:
            text: The input text to split
            allowed_special: Set of special tokens allowed in the encoding
            
        Returns:
            List of text chunks
        """
        if not text:
            return []
            
        try:
            tokens = self.tokenizer.encode(text, allowed_special=allowed_special or set())
            sentences = self.split_into_sentences(tokens)
            return self.merge_sentences_into_chunks(sentences)
        except Exception as e:
            raise RuntimeError(f"Error splitting text: {e}")


def split_chunks(
    text: str, 
    terminators: List[str] = None, 
    min_length: int = 128, 
    max_length: int = 512
) -> List[str]:
    """
    Legacy function for backwards compatibility.
    
    Args:
        text: The input text to split
        terminators: List of characters that mark sentence boundaries
        min_length: Minimum token length for a chunk
        max_length: Maximum token length for a chunk
        
    Returns:
        List of text chunks
    """
    chunker = TextChunker(
        terminators=set(terminators or TextChunker.DEFAULT_TERMINATORS),
        min_length=min_length,
        max_length=max_length
    )
    return chunker.split_text(text)

# if __name__ == "__main__":
#     text = "橡胶产业可谓是国民经济的重要支柱，它那琳琅满目的产品系列早已渗透进我们生活的方方面面。不管是我们触手可及的日用品，还是关乎生命的医疗器械，都离不开这个行业的默默付出。更令人惊叹的是，在新兴产业以及采掘、运输、建设等重工业领域，橡胶的身影更是无处不在，扮演着举足轻重的角色。要知道，固体橡胶那庞大的分子量实在令人咋舌，从数十万到百万级的数值跨度，着实让人印象深刻。然而，要想将这些原料变成实用的制品，就不得不经历切胶、破解、塑化等一系列繁琐工序，这个过程不仅耗时耗力，还白白消耗了大量能源。更让人头疼的是，经过硫化处理的橡胶制品几乎无法进行二次加工和循环利用，一旦被丢弃，不仅造成资源的无谓浪费，还会给我们赖以生存的环境带来难以消除的污染。"
#     chunks = split_chunks(text, min_length=50, max_length=100)
#     print(chunks)
#     """
#     ['橡胶产业可谓是国民经济的重要支柱，它那琳琅满目的产品系列早已渗透进我们生活的方方面面。不管是我们触手可及的日用品，还是关乎生命的医疗器械，都离不开这个行业的默默付出。', '更令人惊叹的是，在新兴产业以及采掘、运输、建设等重工业领域，橡胶的身影更是无处不在，扮演着举足轻重的角色。要知道，固体橡胶那庞大的分子量实在令人咋舌，从数十万到百万级的数值跨度，着实让人印象深刻。然而，要想将这些原料变成实用的', '制品，就不得不经历切胶、破解、塑化等一系列繁琐工序，这个过程不仅耗时耗力，还白白消耗了大量能源。更让人头疼的是，经过硫化处理的橡胶制品几乎无法进行二次加工和循环利用，一旦被丢弃，不仅造成资源的无谓浪费，还会给我们赖以生存的环境带来难以消除的污染。']
#     """




def rank_text_by_score(text_1: str, text_2: List[str], api_url: str = DEFAULT_SCORE_API_URL) -> str:
    if not text_2:
        logger.info("rank_text_by_score 接收到空的 text_2 列表")
        return ""
    
    headers = {
        "Content-Type": "application/json"
    }
    data = {
        "model": "listconranker",
        "text_1": text_1,
        "text_2": text_2
    }

    try:
        response = requests.post(api_url, json=data, headers=headers)
        response.raise_for_status()  # Raise an exception for HTTP errors (4xx or 5xx)
        result = response.json()
        scores_data = result.get("data", [])
        
        if not scores_data:
            logger.info(f"API未返回分数数据。text_1: {text_1[:50]}...")
            return text_2[0]

        # Ensure scores are processed correctly and matched with original texts by index
        scored_texts = []
        for item in scores_data:
            idx = item.get("index")
            score = item.get("score")
            if idx is not None and score is not None and 0 <= idx < len(text_2):
                scored_texts.append((text_2[idx], score))
            else:
                # Log or handle invalid item structure from API
                logger.info(f"Warning: Invalid item from scoring API: {item}")
        
        if not scored_texts: # If, after validation, no valid scored_texts were created
             logger.info(f"从API返回的数据中未能解析出有效的评分项。text_1: {text_1[:50]}...")
             return text_2[0]

        # Sort by score in descending order
        scored_texts.sort(key=lambda x: x[1], reverse=True)
        
        return scored_texts[0][0] # Return the text of the highest-scored item
    
    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP错误: {e}. URL: {api_url}. text_1: {text_1[:50]}...")
        if e.response is not None:
            logger.error(f"服务器响应: {e.response.text}")
        return text_2[0]
    except requests.exceptions.RequestException as e:
        logger.error(f"请求错误: {e}. URL: {api_url}. text_1: {text_1[:50]}...")
        return text_2[0]
    except json.JSONDecodeError as e:
        logger.error(f"JSON解码错误: {e}. URL: {api_url}. text_1: {text_1[:50]}...")
        return text_2[0]
    except Exception as e:
        # Catch any other unexpected errors
        logger.error(f"rank_text_by_score 发生未知错误: {e}. text_1: {text_1[:50]}...")
        return text_2[0]


def main_processing(
    input_json_path: str = DEFAULT_INPUT_JSON_PATH,
    output_json_path: str = DEFAULT_OUTPUT_JSON_PATH,
    chunk_min_length: int = DEFAULT_CHUNK_MIN_LENGTH,
    chunk_max_length: int = DEFAULT_CHUNK_MAX_LENGTH,
    score_api_url: str = DEFAULT_SCORE_API_URL
):
    """
    主处理逻辑：加载数据，对内容进行分块和评分，然后保存结果。
    """
    try:
        with open(input_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        logger.error(f"输入文件未找到: {input_json_path}")
        return
    except json.JSONDecodeError:
        logger.error(f"无法解码JSON文件: {input_json_path}")
        return
    except Exception as e:
        logger.error(f"加载输入文件时发生错误 {input_json_path}: {e}")
        return

    # data = data[:2] # 保留此行用于调试，但默认注释掉
    for item in tqdm(data, desc="Processing items"):
        question = item.get("问题")
        web_result = item.get("web_result")

        if question is None or web_result is None:
            logger.warning(f"跳过缺少 '问题' 或 'web_result' 的项目: {item.get('id', '未知ID')}")
            continue

        for web_item in web_result:
            content = web_item.get("content")
            if not content:
                logger.info(f"项目 {item.get('id', '未知ID')} 中的 web_item缺少内容，跳过评分。")
                web_item["scored_text"] = ""
                continue
            
            chunks = split_chunks(content, min_length=chunk_min_length, max_length=chunk_max_length)
            if not chunks:
                logger.info(f"内容分块后为空，问题: {question[:50]}... 将为scored_text赋空值")
                web_item["scored_text"] = ""
                continue
            
            # 更新 rank_text_by_score 以使用可配置的URL
            scored_text = rank_text_by_score(question, chunks, api_url=score_api_url)
            # 如果 scored_text 为空 (表示评分失败或无有效块)，则 web_item["scored_text"] 将被设为空字符串
            web_item["scored_text"] = scored_text
        item["web_result"] = web_result

    try:
        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        logger.info(f"成功保存到 {output_json_path}")
    except Exception as e:
        logger.error(f"保存输出文件时发生错误 {output_json_path}: {e}")

if __name__ == "__main__":
    main_processing()
