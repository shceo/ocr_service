import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;

class OCRService {
  static Future<String> extractPassportData(File image) async {
    const apiKey = 'K85845231888957';
    final uri = Uri.parse('https://api.ocr.space/parse/image');

    var request = http.MultipartRequest('POST', uri)
      ..fields['apikey'] = apiKey
      ..fields['ocrEngine'] = '2'
      ..files.add(await http.MultipartFile.fromPath('file', image.path));

    try {
      final response = await request.send();
      final responseBody = await response.stream.bytesToString();

      if (response.statusCode == 200) {
        final result = jsonDecode(responseBody);
        if (result['ParsedResults'] != null &&
            result['ParsedResults'].isNotEmpty) {
          final recognizedText = result['ParsedResults'][0]['ParsedText'];
          return recognizedText ?? 'Ошибка: текст не распознан';
        } else {
          return 'Ошибка: данные не распознаны';
        }
      } else {
        return 'Ошибка при обработке OCR: ${response.reasonPhrase}';
      }
    } catch (e) {
      return 'Ошибка при выполнении запроса: $e';
    }
  }
}


