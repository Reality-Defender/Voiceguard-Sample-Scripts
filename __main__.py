import argparse
import os
import hashlib
import mimetypes
import requests
from typing import Dict, Any, List, Optional
import csv
import json
from pathlib import Path
from tqdm import tqdm
from datetime import datetime
import time
from pydub import AudioSegment
import re
import logging

# Configure logging
logger = logging.getLogger(__name__)

class FileProcessor:
    """
    A class for processing files through the VoiceGuard backend system.
    
    This class handles file uploads, blob creation, and file processing through
    a series of GraphQL mutations to the backend service.
    
    Attributes:
        backend_url (str): The URL endpoint for the backend GraphQL API
    """

    def __init__(self, backend_url: str = "https://voiceguard.dev.api.realitydefender.xyz/query", api_key: str = None) -> None:
        """
        Initialize the FileProcessor with a backend URL and API key.

        Args:
            backend_url (str): The URL endpoint for the backend GraphQL API
            api_key (str): API key for authentication (required only for non-localhost URLs)
        """
        self.backend_url = backend_url
        self.api_key = api_key or os.getenv('API_KEY')
        
        # Check if backend URL is localhost or 127.0.0.1
        is_localhost = 'localhost' in self.backend_url or '127.0.0.1' in self.backend_url
        
        # Only require API key for non-localhost URLs
        if not is_localhost and not self.api_key:
            raise ValueError("API key must be provided either as argument or through API_KEY environment variable for non-localhost URLs")
        
    def calculate_sha256(self, file_path: str) -> str:
        """
        Calculate the SHA256 hash of a file.

        Args:
            file_path (str): Path to the file to hash

        Returns:
            str: Hexadecimal representation of the SHA256 hash
        """
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    
    def get_file_info(self, file_path: str) -> Dict[str, Any]:
        """
        Gather metadata about a file including its content type, size, name, and hash.

        Args:
            file_path (str): Path to the file to analyze

        Returns:
            Dict[str, Any]: Dictionary containing file metadata:
                - contentType: MIME type of the file
                - contentLength: Size of the file in bytes
                - fileName: Name of the file
                - sha256: SHA256 hash of the file
        """
        content_type, _ = mimetypes.guess_type(file_path)
        if not content_type:
            content_type = "application/octet-stream"
            
        # Sanitize filename: replace spaces and special characters
        filename = os.path.basename(file_path)
        safe_filename = re.sub(r'[^\w.-]', '_', filename)
        
        return {
            "contentType": content_type,
            "contentLength": os.path.getsize(file_path),
            "fileName": safe_filename,
            "sha256": self.calculate_sha256(file_path)
        }
    
    def create_file_blob(self, file_info: Dict[str, Any]) -> Dict[str, str]:
        """
        Create a file blob entry in the backend system via GraphQL mutation.

        Args:
            file_info (Dict[str, Any]): File metadata from get_file_info()

        Returns:
            Dict[str, str]: Response containing:
                - id: The blob ID
                - url: Upload URL for the file
        """
        mutation = """
        mutation($input: CreateFileBlobInput!) {
            createFileBlob(input: $input) {
                id
                url
            }
        }
        """
        
        variables = {
            "input": {
                "contentLength": file_info["contentLength"],
                "contentType": file_info["contentType"],
                "fileName": file_info["fileName"],
                "sha256": file_info["sha256"]
            }
        }
        
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-KEY"] = self.api_key
        
        try:
            logger.debug(f"Sending createFileBlob request to {self.backend_url}")
            response = requests.post(
                self.backend_url,
                json={"query": mutation, "variables": variables},
                headers=headers
            )
            
            # Log the raw response for debugging
            logger.debug(f"createFileBlob response status code: {response.status_code}")
            
            if response.status_code != 200:
                logger.error(f"Request failed with status code {response.status_code}")
                logger.error(f"Response content: {response.text}")
                return None
            
            response_data = response.json()
            
            # Check for GraphQL errors
            if "errors" in response_data:
                errors = response_data.get("errors", [])
                error_messages = [error.get("message", "Unknown error") for error in errors]
                logger.error(f"GraphQL errors: {', '.join(error_messages)}")
                return None
            
            # Check if data exists and has expected structure
            if "data" not in response_data:
                logger.error(f"Missing 'data' in response: {response_data}")
                return None
            
            if "createFileBlob" not in response_data["data"]:
                logger.error(f"Missing 'createFileBlob' in response data: {response_data['data']}")
                return None
            
            result = response_data["data"]["createFileBlob"]
            
            # Verify result has expected keys
            if "id" not in result or "url" not in result:
                logger.error(f"Missing required fields in result: {result}")
                return None
            
            return result
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Request exception in createFileBlob: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in createFileBlob: {str(e)}")
            return None
    
    def upload_file(self, file_path: str, upload_url: str, file_info: Dict[str, Any]) -> None:
        """
        Upload a file to the specified URL with appropriate headers.

        Args:
            file_path (str): Path to the file to upload
            upload_url (str): URL to upload the file to
            file_info (Dict[str, Any]): File metadata from get_file_info()

        Raises:
            requests.exceptions.RequestException: If the upload fails
        """
        headers = {
            "Content-Type": file_info["contentType"],
            "Content-Length": str(file_info["contentLength"]),
            "X-Amz-Content-Sha256": file_info["sha256"]
        }
        
        with open(file_path, "rb") as f:
            response = requests.put(upload_url, data=f, headers=headers)
        response.raise_for_status()
        
    def create_files(self, file_blob_id: str) -> Dict[str, List[Dict[str, str]]]:
        """
        Create file entries in the backend system from uploaded blobs.

        Args:
            file_blob_id (str): ID of the previously created file blob

        Returns:
            Dict[str, List[Dict[str, str]]]: Response containing:
                - files: List of created files with their IDs
        """
        mutation = """
        mutation($input: CreateFilesInput!) {
            createFiles(input: $input) {
                files {
                    id
                }
            }
        }
        """
        
        variables = {
            "input": {
                "fileBlobIds": [file_blob_id],
                "processingRequestType": "WITHOUT_CORRUPTION"
            }
        }
        
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-KEY"] = self.api_key
        
        try:
            logger.debug(f"Sending createFiles request with blob ID: {file_blob_id}")
            response = requests.post(
                self.backend_url,
                json={"query": mutation, "variables": variables},
                headers=headers
            )
            
            # Log the raw response for debugging
            logger.debug(f"createFiles response status code: {response.status_code}")
            
            if response.status_code != 200:
                logger.error(f"Request failed with status code {response.status_code}")
                logger.error(f"Response content: {response.text}")
                return None
            
            response_data = response.json()
            
            # Check for GraphQL errors
            if "errors" in response_data:
                errors = response_data.get("errors", [])
                error_messages = [error.get("message", "Unknown error") for error in errors]
                logger.error(f"GraphQL errors: {', '.join(error_messages)}")
                return None
            
            # Check if data exists and has expected structure
            if "data" not in response_data:
                logger.error(f"Missing 'data' in response: {response_data}")
                return None
            
            if "createFiles" not in response_data["data"]:
                logger.error(f"Missing 'createFiles' in response data: {response_data['data']}")
                return None
            
            result = response_data["data"]["createFiles"]
            
            # Verify result has expected keys
            if "files" not in result:
                logger.error(f"Missing 'files' key in result: {result}")
                return None
            
            return result
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Request exception in createFiles: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in createFiles: {str(e)}")
            return None
    
    def get_stream_status(self, file_id: str) -> Optional[tuple[str, float, str]]:
        """
        Query the stream status for a given file ID from the backend system.

        Args:
            file_id (str): The unique identifier of the file to query

        Returns:
            Optional[tuple[str, float, str]]: Tuple of (conclusion, probability, reason) if processing is complete, None otherwise
        """
        query = """
        query GetStreamByOriginalFileId($fileId: SortableID!) {
            getStreamByOriginalFileId(originalFileId: $fileId) {
                id
                direction
                fromPhoneNumber
                toPhoneNumber
                streamStatus
                streamResult {
                    conclusion
                    probability
                    millisecondsToConclusion
                }
                segments {
                    modelResults {
                        conclusion
                    }
                    preprocessingResult {
                        preprocessingConclusion
                    }
                }
            }
        }
        """
        
        variables = {
            "fileId": file_id
        }
        
        try:
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["X-API-KEY"] = self.api_key
            
            response = requests.post(
                self.backend_url,
                json={"query": query, "variables": variables},
                headers=headers
            )
            
            # Log raw response for debugging
            if response.status_code != 200:
                logger.debug(f"Error response for file {file_id}: Status code {response.status_code}")
                logger.debug(f"Response content: {response.text[:500]}...")  # Limit to first 500 chars
                return None
            
            response_data = response.json()
            
            # Check for GraphQL errors
            if "errors" in response_data:
                errors = response_data.get("errors", [])
                error_messages = [error.get("message", "Unknown error") for error in errors]
                logger.debug(f"GraphQL errors for file {file_id}: {', '.join(error_messages)}")
                return None
                
            # Get stream data with safer dictionary access
            data = response_data.get("data", {})
            if not data:
                logger.debug(f"No data returned for file {file_id}")
                return None
                
            stream_data = data.get("getStreamByOriginalFileId")
            if not stream_data:
                logger.debug(f"No stream found for file {file_id}")
                return None
            
            # Check stream status and conclusion with safer dictionary access
            stream_id = stream_data.get("id")
            stream_status = stream_data.get("streamStatus")
            stream_result = stream_data.get("streamResult", {})

            if stream_status == "COMPLETED" and stream_result and stream_result.get("conclusion"):
                reason = ""
                if stream_result["conclusion"] == "INCONCLUSIVE":
                    # Get all preprocessing conclusions
                    segments = stream_data.get("segments", [])
                    preprocessing_conclusions = []                                        
                    for segment in segments:
                        preprocessing = segment.get("preprocessingResult", {})
                        if preprocessing and preprocessing.get("preprocessingConclusion"):
                            preprocessing_conclusions.append(preprocessing["preprocessingConclusion"])
                    
                    # Join all unique preprocessing conclusions
                    if preprocessing_conclusions:
                        unique_conclusions = list(dict.fromkeys(preprocessing_conclusions))  # Remove duplicates while preserving order
                        reason = ", ".join(unique_conclusions)
                
                return (stream_result["conclusion"], stream_result.get("probability", -1), reason, stream_id)          
            
            return None
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error for file {file_id}: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error for file {file_id}: {str(e)}")
            return None
    
    def get_detailed_stream(self, file_id: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed stream information including all fields from segments, model results, etc.
        Uses a progressive approach with fallbacks for stability.
        
        Args:
            file_id (str): The unique identifier of the file to query
            
        Returns:
            Optional[Dict[str, Any]]: Complete stream data if available, None otherwise
        """
        # First try with the basic query - this has the highest chance of success
        logger.debug("Attempting basic stream query...")
        basic_data = self._get_basic_stream(file_id)
        
        if not basic_data:
            logger.debug("Basic query failed, cannot proceed")
            return None
            
        # If basic query succeeds, try to enrich with segment data
        retry_count = 0
        max_retries = 100
        backoff_seconds = 1
            
        while retry_count < max_retries:
            try:
                logger.debug(f"Attempting to retrieve detailed segment data (attempt {retry_count+1}/{max_retries})...")
                
                enriched_data = self._get_detailed_stream_simplified(file_id)
                
                if enriched_data:
                    logger.debug("Successfully retrieved enriched stream data")
                    return enriched_data
                    
                # If we got here, the enriched query failed but we still have basic data
                retry_count += 1
                logger.debug(f"Enriched query failed, backing off for {backoff_seconds} seconds")
                time.sleep(backoff_seconds)
                backoff_seconds *= 2  # Exponential backoff
                
            except Exception as e:
                logger.error(f"Error during enriched query: {str(e)}")
                retry_count += 1
                time.sleep(backoff_seconds)
                backoff_seconds *= 2
                
        logger.debug("Falling back to basic stream data")
        return basic_data
    
    def _get_basic_stream(self, file_id: str) -> Optional[Dict[str, Any]]:
        """
        Get minimal stream information - just the core fields without complex nested structures.
        This is the most reliable query with the highest chance of success.
        
        Args:
            file_id (str): The unique identifier of the file to query
            
        Returns:
            Optional[Dict[str, Any]]: Basic stream data if available, None otherwise
        """
        query = """
        query GetStreamByOriginalFileId($fileId: SortableID!) {
            getStreamByOriginalFileId(originalFileId: $fileId) {
                id
                callType
                direction
                streamStatus
                createdAt
                updatedAt
                streamResult {
                    conclusion
                    probability
                    millisecondsToConclusion
                }
            }
        }
        """
        
        variables = {
            "fileId": file_id
        }
        
        try:
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["X-API-KEY"] = self.api_key
                
            response = requests.post(
                self.backend_url,
                json={"query": query, "variables": variables},
                headers=headers
            )
            
            if response.status_code != 200:
                logger.debug(f"Basic query failed: Status code {response.status_code}")
                return None
                
            response_data = response.json()
            
            if "errors" in response_data:
                errors = response_data.get("errors", [])
                error_messages = [error.get("message", "Unknown error") for error in errors]
                logger.debug(f"GraphQL errors in basic query: {', '.join(error_messages)}")
                return None
                
            data = response_data.get("data", {})
            stream_data = data.get("getStreamByOriginalFileId")
            
            return stream_data
            
        except Exception as e:
            logger.error(f"Error in basic query: {str(e)}")
            return None
    
    def _get_enriched_stream_with_segments(self, file_id: str) -> Optional[Dict[str, Any]]:
        """
        Get stream information enriched with segment data, but still keeping it minimal.
        
        Args:
            file_id (str): The unique identifier of the file to query
            
        Returns:
            Optional[Dict[str, Any]]: Enriched stream data if available, None otherwise
        """
        query = """
        query GetStreamByOriginalFileId($fileId: SortableID!) {
            getStreamByOriginalFileId(originalFileId: $fileId) {
                id
                callType
                direction
                fromPhoneNumber
                toPhoneNumber
                streamStatus
                sipCallID
                createdAt
                updatedAt
                streamResult {
                    conclusion
                    probability
                    millisecondsToConclusion
                    createdAt
                    updatedAt
                }
                segments {
                    id
                    preprocessingResult {
                        preprocessingConclusion
                        language
                    }
                    modelResults {
                        modelName
                        modelVersion
                        conclusion
                        probability
                    }
                    result {
                        conclusion
                        probability
                    }
                }
            }
        }
        """
        
        variables = {
            "fileId": file_id
        }
        
        try:
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["X-API-KEY"] = self.api_key
                
            response = requests.post(
                self.backend_url,
                json={"query": query, "variables": variables},
                headers=headers
            )
            
            if response.status_code != 200:
                logger.debug(f"Enriched query failed: Status code {response.status_code}")
                return None
                
            response_data = response.json()
            
            if "errors" in response_data:
                errors = response_data.get("errors", [])
                error_messages = [error.get("message", "Unknown error") for error in errors]
                logger.debug(f"GraphQL errors in enriched query: {', '.join(error_messages)}")
                return None
                
            data = response_data.get("data", {})
            stream_data = data.get("getStreamByOriginalFileId")
            
            return stream_data
            
        except Exception as e:
            logger.error(f"Error in enriched query: {str(e)}")
            return None
            
    def _get_detailed_stream_simplified(self, file_id: str) -> Optional[Dict[str, Any]]:
        """
        Get minimal stream information as a last-resort fallback.
        
        Args:
            file_id (str): The unique identifier of the file to query
            
        Returns:
            Optional[Dict[str, Any]]: Minimal stream data if available, None otherwise
        """
        query = """
        query GetStreamByOriginalFileId($fileId: SortableID!) {
            getStreamByOriginalFileId(originalFileId: $fileId) {
                id
                streamStatus
                streamResult {
                    conclusion
                    probability
                }
                segments {
                    id
                    preprocessingResult {
                        preprocessingConclusion
                        language {
                            language
                            supported
                        }
                        millisecondsToConclusion
                    }
                    modelResults {
                        modelName
                        modelVersion    
                        conclusion
                        probability
                        millisecondsToConclusion
                    }
                    result {
                        conclusion
                        probability
                        millisecondsToConclusion
                    }
                }
            }
        }
        """
        
        variables = {
            "fileId": file_id
        }
        
        try:
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["X-API-KEY"] = self.api_key
                
            response = requests.post(
                self.backend_url,
                json={"query": query, "variables": variables},
                headers=headers
            )
            
            if response.status_code != 200:
                logger.debug(f"Simplified query failed: Status code {response.status_code}")
                return None
                
            response_data = response.json()
            
            if "errors" in response_data:
                errors = response_data.get("errors", [])
                error_messages = [error.get("message", "Unknown error") for error in errors]
                logger.debug(f"GraphQL errors in simplified query: {', '.join(error_messages)}")
                return None
                
            data = response_data.get("data", {})
            stream_data = data.get("getStreamByOriginalFileId")
            
            if stream_data:
                logger.debug(f"Successfully retrieved simplified stream data")
                
            return stream_data
            
        except Exception as e:
            logger.error(f"Error in simplified query: {str(e)}")
            return None

    def process_file(self, file_path: str, csv_path: Optional[Path], json_path: Optional[Path]) -> None:
        """
        Process a single file through the backend system and record results in CSV and/or JSON.
        Waits for processing completion before returning.
        
        Args:
            file_path (str): Path to the file to process
            csv_path (Optional[Path]): Path to the CSV file for results, or None if CSV output is disabled
            json_path (Optional[Path]): Path to the JSON file for detailed results, or None if JSON output is disabled
        """
        try:
            # Initialize CSV if requested and doesn't exist
            if csv_path:
                file_exists = csv_path.exists()
                with open(csv_path, 'a', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=['original_filename', 'file_id', 'stream_id', 'status', 'conclusion', 'probability', 'reason'])
                    if not file_exists:
                        writer.writeheader()
                    
                    # Add initial row with UPLOADING status
                    writer.writerow({
                        'original_filename': file_path,
                        'file_id': '',  # Empty as we don't have it yet
                        'stream_id': '',
                        'status': 'UPLOADING',
                        'conclusion': '',
                        'probability': -1,
                        'reason': ''
                    })

            # Process file
            file_info = self.get_file_info(file_path)
            logger.debug(f"Processing file: {file_info['fileName']} ({file_info['contentType']}, {file_info['contentLength']} bytes)")
            
            blob_data = self.create_file_blob(file_info)
            logger.debug(f"Created file blob with ID: {blob_data['id']}")
            
            self.upload_file(file_path, blob_data["url"], file_info)
            logger.debug(f"Uploaded file to blob storage")
            
            files_data = self.create_files(blob_data["id"])
            
            # Check if files_data is None or doesn't have the expected structure
            if not files_data or 'files' not in files_data or not files_data['files']:
                raise Exception("Failed to create file in backend system")
            
            file_id = files_data["files"][0]["id"]
            logger.debug(f"Created file with ID: {file_id}")
            
            # Update status to PROCESSING after upload if CSV output is enabled
            if csv_path:
                self._update_csv_status(csv_path, file_path, file_id, 'PROCESSING')

            # Wait for processing to complete
            file_duration = self._get_file_duration(file_path)
            timeout = (file_duration or 180) + 60
            start_time = time.time()
            
            logger.debug(f"Waiting for processing to complete (timeout: {timeout}s)...")
            
            while True:
                result = self.get_stream_status(file_id)
                if result:
                    conclusion, probability, reason, stream_id = result
                    logger.debug(f"Processing complete: {conclusion} (probability: {probability})")
                    
                    # Update CSV if requested
                    if csv_path:
                        self._update_csv_conclusion(csv_path, file_id, stream_id, conclusion, probability, reason)
                    
                    # Get detailed stream data and save to JSON if requested
                    if json_path:
                        logger.debug(f"Fetching detailed stream data...")
                        detailed_stream = self.get_detailed_stream(file_id)
                        if detailed_stream:
                            self._update_json_results(json_path, file_path, file_id, detailed_stream)
                            logger.debug(f"Saved detailed stream data to JSON")
                        else:
                            logger.warning(f"Could not fetch detailed stream data")
                    break
                
                if time.time() - start_time > timeout:
                    logger.warning(f"Processing timed out after {timeout}s")
                    if csv_path:
                        self._update_csv_conclusion(csv_path, file_id, stream_id, "INCONCLUSIVE", -1, "TIMEOUT")
                    break
                
                time.sleep(2)  # Reduced polling frequency to avoid rate limiting
                
        except Exception as e:
            # Update CSV with error status if CSV output is enabled
            logger.error(f"Error processing file {file_path}: {str(e)}")
            if csv_path:
                with open(csv_path, 'a', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=['original_filename', 'file_id', 'stream_id', 'status', 'conclusion', 'probability', 'reason'])
                    writer.writerow({
                        'original_filename': file_path,
                        'file_id': '',
                        'stream_id': '',
                        'status': 'ERROR',
                        'conclusion': '',
                        'probability': -1,
                        'reason': str(e)
                    })

    def _get_file_duration(self, file_path: str) -> Optional[float]:
        """
        Get the duration of an audio file in seconds.
        
        Args:
            file_path (str): Path to the audio file
            
        Returns:
            Optional[float]: Duration in seconds if successful, None if failed
        """
        try:
            audio = AudioSegment.from_file(file_path)
            return audio.duration_seconds
        except Exception as e:
            logger.warning(f"Could not determine file duration for {file_path}: {str(e)}")
            return None

    def _update_csv_conclusion(self, csv_path: Path, file_id: str, stream_id: str, conclusion: str, probability: float, reason: str) -> None:
        """Helper method to update a file's conclusion in the CSV."""
        updated_rows = []
        with open(csv_path, 'r', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row['file_id'] == file_id:
                    row['stream_id'] = stream_id
                    row['conclusion'] = conclusion
                    row['probability'] = probability
                    row['reason'] = reason
                    row['status'] = 'COMPLETED'
                updated_rows.append(row)
        
        with open(csv_path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['original_filename', 'file_id', 'stream_id', 'status', 'conclusion', 'probability', 'reason'])
            writer.writeheader()
            writer.writerows(updated_rows)

    def _update_csv_status(self, csv_path: Path, original_filename: str, file_id: str, status: str) -> None:
        """Helper method to update a file's status in the CSV."""
        updated_rows = []
        with open(csv_path, 'r', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row['original_filename'] == original_filename and row['file_id'] == '':
                    row['file_id'] = file_id
                    row['status'] = status
                updated_rows.append(row)
        
        with open(csv_path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['original_filename', 'file_id', 'stream_id', 'status', 'conclusion', 'probability', 'reason'])
            writer.writeheader()
            writer.writerows(updated_rows)
    
    def _update_json_results(self, json_path: Path, original_filename: str, file_id: str, stream_data: Dict[str, Any]) -> None:
        """
        Helper method to update the JSON file with detailed stream data.
        
        Args:
            json_path (Path): Path to the JSON file
            original_filename (str): Original file path
            file_id (str): File ID from the backend
            stream_data (Dict[str, Any]): Detailed stream data to save
        """
        # Create a result object with metadata and stream data
        result_object = {
            "original_filename": original_filename,
            "file_id": file_id,
            "analyzed_at": datetime.now().isoformat(),
            "stream_data": stream_data
        }
        
        # Load existing data if file exists
        existing_data = []
        if json_path.exists() and json_path.stat().st_size > 0:
            try:
                with open(json_path, 'r') as f:
                    existing_data = json.load(f)
            except json.JSONDecodeError:
                logger.warning(f"Warning: Could not parse existing JSON file {json_path}. Creating new file.")
                existing_data = []
        
        # Check if this file_id already exists in the data
        for i, item in enumerate(existing_data):
            if item.get('file_id') == file_id:
                existing_data[i] = result_object
                break
        else:
            # If not found, append the new result
            existing_data.append(result_object)
        
        # Save the updated data back to the file
        with open(json_path, 'w') as f:
            json.dump(existing_data, f, indent=2)

def main() -> None:
    """Main entry point for the file processing script."""
    # Set up logging configuration with console only (no log file)
    
    # Create console handler with INFO level (only show important messages)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # Create formatter
    formatter = logging.Formatter('%(levelname)s: %(message)s')
    console_handler.setFormatter(formatter)
    
    # Configure root logger - still capture DEBUG for the code, but only display INFO+
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Log everything internally
    root_logger.addHandler(console_handler)
    
    # Silence tqdm logging
    logging.getLogger('tqdm').setLevel(logging.WARNING)
    
    parser = argparse.ArgumentParser(description="Process files for VoiceGuard backend")
    parser.add_argument("directory", help="Directory containing files to process")
    parser.add_argument(
        "--extensions",
        nargs="+",
        default=[".wav"],
        help="List of allowed file extensions (e.g. .wav .mp3). Default: .wav"
    )
    parser.add_argument(
        "--api-key",
        help="API key for authentication (required for non-localhost URLs, can also be set via API_KEY environment variable)"
    )
    parser.add_argument(
        "--backend-url",
        default="https://app.api.voiceguard.realitydefender.xyz/query",
        help="Backend URL (can also be set via BACKEND_URL environment variable)"
    )
    parser.add_argument(
        "--output",
        nargs="+",
        default=["csv"],
        choices=["csv", "json", "both"],
        help="Output format(s): 'csv', 'json', or 'both' (or 'csv json'). Default: csv"
    )
    args = parser.parse_args()
    
    if not os.path.isdir(args.directory):
        logger.error(f"Error: {args.directory} is not a valid directory")
        return
    
    # Check if backend URL is non-localhost and no API key is provided
    backend_url = args.backend_url or os.getenv('BACKEND_URL', "https://app.api.voiceguard.realitydefender.xyz/query")
    api_key = args.api_key or os.getenv('API_KEY')
    is_localhost = 'localhost' in backend_url or '127.0.0.1' in backend_url
    
    if not is_localhost and not api_key:
        logger.warning("Warning: You are using a non-localhost URL without providing an API key.")
        logger.warning("API requests may fail. Use --api-key or set the API_KEY environment variable.")
    
    # Normalize extensions to include dot and lowercase
    allowed_extensions = [ext.lower() if ext.startswith('.') else f'.{ext.lower()}' for ext in args.extensions]
    
    # Create timestamped results filenames
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Determine which output formats to use
    use_csv = "csv" in args.output or "both" in args.output
    use_json = "json" in args.output or "both" in args.output
    
    # Create output file paths if needed
    results_csv_path = Path(f"results_{timestamp}.csv") if use_csv else None
    results_json_path = Path(f"results_{timestamp}.json") if use_json else None
    
    # Display which outputs will be generated
    outputs = []
    if use_csv:
        outputs.append(f"CSV: {results_csv_path}")
    if use_json:
        outputs.append(f"JSON: {results_json_path}")
    logger.info(f"Output will be saved to: {', '.join(outputs)}")
    
    processor = FileProcessor(backend_url=backend_url, api_key=api_key)
    
    # Recursively get all files in directory and subdirectories with allowed extensions
    files_to_process = [
        str(f) for f in Path(args.directory).rglob("*") 
        if f.is_file() and f.suffix.lower() in allowed_extensions
    ]
    
    if not files_to_process:
        logger.warning(f"No files found with allowed extensions: {', '.join(allowed_extensions)}")
        return
    
    # Initialize empty JSON file if needed
    if results_json_path:
        with open(results_json_path, 'w') as f:
            json.dump([], f)
    
    # Process files one at a time with progress bar
    # Use tqdm directly to console (will show at INFO level)
    with tqdm(total=len(files_to_process), desc="Processing files", unit="file") as pbar:
        for file_path in files_to_process:
            processor.process_file(file_path, results_csv_path, results_json_path)
            pbar.update(1)
    
    # Print completion message - display at INFO level
    logger.info("\n✨ Processing complete! Results saved to:")
    if use_csv:
        logger.info(f"   - CSV: {results_csv_path}")
    if use_json:
        logger.info(f"   - JSON: {results_json_path}")

if __name__ == "__main__":
    main()
