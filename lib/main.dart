import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'dart:io';
import 'dart:convert';
import 'package:image_picker/image_picker.dart';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';

void main() {
  runApp(const MyApp());
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});
  @override
  Widget build(BuildContext context) {
    return const MaterialApp(
      debugShowCheckedModeBanner: false,
      home: LoginScreen(),
    );
  }
}

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});
  @override
  _LoginScreenState createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _passwordController = TextEditingController();
  String? _error;

  Future<void> _login() async {
    SharedPreferences prefs = await SharedPreferences.getInstance();
    // Если пароль ещё не был сохранён, по умолчанию он "1234"
    String storedPassword = prefs.getString('password') ?? '1234';

    if (_passwordController.text == storedPassword) {
      Navigator.pushReplacement(
        context,
        MaterialPageRoute(builder: (context) => const HomeScreen()),
      );
    } else {
      setState(() {
        _error = 'Неверный пароль';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final buttonWidth = MediaQuery.of(context).size.width * 0.8;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Вход'),
        centerTitle: true,
      ),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(16.0),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              TextField(
                controller: _passwordController,
                obscureText: true,
                maxLength: 4,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(
                  labelText: 'Введите 4-значный пароль',
                  border: OutlineInputBorder(),
                ),
              ),
              if (_error != null)
                Text(
                  _error!,
                  style: const TextStyle(color: Colors.red),
                ),
              const SizedBox(height: 20),
              SizedBox(
                width: buttonWidth,
                height: 50,
                child: ElevatedButton(
                  onPressed: _login,
                  child: const Text('Войти'),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});
  @override
  _HomeScreenState createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int _currentIndex = 0;
  final List<Widget> _pages = [
    const PassportReaderScreen(),
    const SettingsScreen(),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: _pages[_currentIndex],
      floatingActionButtonLocation: FloatingActionButtonLocation.centerDocked,
      floatingActionButton: Container(
        margin: const EdgeInsets.only(bottom: 20, left: 16, right: 16),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(24),
          boxShadow: const [
            BoxShadow(color: Colors.black26, blurRadius: 8),
          ],
        ),
        child: BottomNavigationBar(
          currentIndex: _currentIndex,
          onTap: (index) => setState(() => _currentIndex = index),
          items: const [
            BottomNavigationBarItem(icon: Icon(Icons.home), label: 'Главная'),
            BottomNavigationBarItem(
                icon: Icon(Icons.settings), label: 'Настройки'),
          ],
          backgroundColor: Colors.transparent,
          elevation: 0,
          selectedItemColor: Colors.blue,
          unselectedItemColor: Colors.grey,
          type: BottomNavigationBarType.fixed,
        ),
      ),
    );
  }
}

class PassportReaderScreen extends StatefulWidget {
  const PassportReaderScreen({super.key});
  @override
  _PassportReaderScreenState createState() => _PassportReaderScreenState();
}

class _PassportReaderScreenState extends State<PassportReaderScreen> {
  File? _image;
  bool _isProcessing = false;
  String? _error;
  String? _excelPath;

  Future<void> _pickImage() async {
    final picked = await ImagePicker().pickImage(source: ImageSource.gallery);
    if (picked == null) return;

    // Спрашиваем имя файла
    final fileName = await _askFileName();
    if (fileName == null || fileName.isEmpty) return;

    setState(() {
      _image = File(picked.path);
      _isProcessing = true;
      _error = null;
    });
    try {
      // отправляем на сервер с указанием имени
      final uri = Uri.parse('https://ocr-service-oj4v.onrender.com/process');
      final request = http.MultipartRequest('POST', uri)
        ..files.add(await http.MultipartFile.fromPath('file', _image!.path))
        ..fields['filename'] = fileName;
      final resp = await request.send();
      if (resp.statusCode != 200) {
        throw Exception('Server error: ${resp.statusCode}');
      }
      final bytes = await resp.stream.toBytes();

      // сохраняем xlsx под тем же именем
      final dir = await getApplicationDocumentsDirectory();
      final file = File('${dir.path}/$fileName');
      await file.writeAsBytes(bytes);

      setState(() {
        _excelPath = file.path;
        _isProcessing = false;
      });
    } catch (e) {
      setState(() {
        _error = 'Ошибка: $e';
        _isProcessing = false;
      });
    }
  }

  Future<String?> _askFileName() async {
    final ctrl = TextEditingController(text: 'passport_data.xlsx');
    return showDialog<String>(
      context: context,
      builder: (c) => AlertDialog(
        title: const Text('Введите имя Excel-файла'),
        content: TextField(
          controller: ctrl,
          decoration: const InputDecoration(hintText: 'например data.xlsx'),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(c, null),
              child: const Text('Отмена')),
          TextButton(
              onPressed: () => Navigator.pop(c, ctrl.text.trim()),
              child: const Text('OK')),
        ],
      ),
    );
  }

  Future<void> _openFolder() async {
    if (_excelPath == null) return;
    final dir = Directory(_excelPath!).parent.path;
    if (Platform.isWindows) {
      await Process.run('explorer', [dir]);
    } else if (Platform.isMacOS) {
      await Process.run('open', [dir]);
    } else {
      await Process.run('xdg-open', [dir]);
    }
  }

  @override
  Widget build(BuildContext context) {
    final buttonWidth = MediaQuery.of(context).size.width * 0.8;
    return Scaffold(
      appBar:
          AppBar(title: const Text('Чтение паспорта РФ'), centerTitle: true),
      body: SingleChildScrollView(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 60, vertical: 35),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              if (_image != null) Image.file(_image!, height: 200),
              const SizedBox(height: 20),
              SizedBox(
                width: buttonWidth,
                height: 50,
                child: ElevatedButton(
                  onPressed: _isProcessing ? null : _pickImage,
                  child: const Text('Загрузить файл'),
                ),
              ),
              const SizedBox(height: 20),
              if (_excelPath != null) ...[
                Text('Excel сохранён: $_excelPath',
                    style: const TextStyle(color: Colors.blue)),
                const SizedBox(height: 20),
                SizedBox(
                  width: buttonWidth,
                  height: 50,
                  child: ElevatedButton(
                    onPressed: _openFolder,
                    child: const Text('Открыть папку'),
                  ),
                ),
              ],
              if (_error != null)
                Text(_error!, style: const TextStyle(color: Colors.red)),
              if (_isProcessing)
                const Padding(
                  padding: EdgeInsets.all(20),
                  child: CircularProgressIndicator(),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class SettingsScreen extends StatelessWidget {
  const SettingsScreen({super.key});
  @override
  Widget build(BuildContext context) {
    final buttonWidth = MediaQuery.of(context).size.width * 0.8;
    return Scaffold(
      appBar: AppBar(title: const Text('Настройки'), centerTitle: true),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: ElevatedButton(
            style: ElevatedButton.styleFrom(
              padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
              shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12)),
            ),
            onPressed: () => Navigator.push(
                context,
                MaterialPageRoute(
                    builder: (_) => const ChangePasswordScreen())),
            child: const Text('Изменить пароль'),
          ),
        ),
      ),
    );
  }
}

class ChangePasswordScreen extends StatefulWidget {
  const ChangePasswordScreen({super.key});
  @override
  _ChangePasswordScreenState createState() => _ChangePasswordScreenState();
}

class _ChangePasswordScreenState extends State<ChangePasswordScreen> {
  final _newPasswordController = TextEditingController();
  String? _message;

  Future<void> _changePassword() async {
    if (_newPasswordController.text.isEmpty) {
      setState(() => _message = 'Пароль не может быть пустым.');
    } else {
      SharedPreferences prefs = await SharedPreferences.getInstance();
      await prefs.setString('password', _newPasswordController.text);
      setState(() => _message = 'Пароль успешно изменён!');
    }
  }

  @override
  Widget build(BuildContext context) {
    final buttonWidth = MediaQuery.of(context).size.width * 0.8;
    return Scaffold(
      appBar: AppBar(title: const Text('Изменить пароль'), centerTitle: true),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              TextField(
                controller: _newPasswordController,
                obscureText: true,
                maxLength: 4,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(
                  labelText: 'Новый 4-значный пароль',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 20),
              SizedBox(
                width: buttonWidth,
                height: 50,
                child: ElevatedButton(
                  onPressed: _changePassword,
                  child: const Text('Сохранить'),
                ),
              ),
              const SizedBox(height: 20),
              if (_message != null)
                Text(_message!, style: const TextStyle(color: Colors.green)),
            ],
          ),
        ),
      ),
    );
  }
}
